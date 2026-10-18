"""Ingestion orchestration: idempotent upserts keyed on natural unique constraints.

Crash-safety model: every write is an `INSERT … ON CONFLICT` upsert and each symbol is
committed in its own transaction, so re-running after a mid-run crash converges to the
same state — no dedupe pass, no partial-state cleanup.
"""

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from filingsdesk.config import get_settings
from filingsdesk.db import Filing, FilingChunk, Instrument, Price, session_scope
from filingsdesk.ingestion.filings import (
    FilingRecord,
    fetch_recent_filings,
    load_fixture_filings,
)
from filingsdesk.ingestion.prices import PriceBar, fetch_daily_prices, synthetic_prices

log = structlog.get_logger(__name__)


def upsert_instrument(session: Session, symbol: str, name: str | None = None) -> Instrument:
    stmt = (
        insert(Instrument)
        .values(symbol=symbol.upper(), name=name or symbol.upper(), currency="USD")
        .on_conflict_do_nothing(index_elements=["symbol"])
    )
    session.execute(stmt)
    return session.scalars(select(Instrument).where(Instrument.symbol == symbol.upper())).one()


def ingest_prices(session: Session, symbol: str, bars: list[PriceBar]) -> int:
    """Upsert bars; conflicting (instrument, date) rows are updated, not duplicated."""
    if not bars:
        return 0
    instrument = upsert_instrument(session, symbol)
    stmt = insert(Price).values(
        [
            {
                "instrument_id": instrument.id,
                "date": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_prices_instrument_date",
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    session.execute(stmt)
    log.info("ingest.prices_upserted", symbol=symbol, bars=len(bars))
    return len(bars)


def ingest_filings(session: Session, records: list[FilingRecord]) -> int:
    """Upsert filings keyed on accession_no; re-chunk only when newly inserted."""
    from filingsdesk.rag.chunking import chunk_filing_text

    settings = get_settings()
    ingested = 0
    for record in records:
        instrument = upsert_instrument(session, record.symbol)
        existing = session.scalars(
            select(Filing).where(Filing.accession_no == record.accession_no)
        ).one_or_none()
        if existing is not None:
            log.info("ingest.filing_exists", accession=record.accession_no)
            continue

        filing = Filing(
            accession_no=record.accession_no,
            instrument_id=instrument.id,
            form_type=record.form_type,
            filed_at=record.filed_at,
            title=record.title,
            body=record.body,
            source_url=record.source_url,
        )
        session.add(filing)
        session.flush()

        chunks = chunk_filing_text(
            record.body,
            strategy=settings.chunking_strategy,
            chunk_size=settings.chunk_size_chars,
            overlap=settings.chunk_overlap_chars,
        )
        for i, chunk in enumerate(chunks):
            session.add(
                FilingChunk(
                    filing_id=filing.id, chunk_index=i, section=chunk.section, text=chunk.text
                )
            )
        ingested += 1
        log.info("ingest.filing_added", accession=record.accession_no, chunks=len(chunks))
    if ingested:
        # pgvector only searches embedded rows, so a filing isn't searchable until this runs.
        from filingsdesk.rag.store import get_vector_store

        session.flush()
        get_vector_store().index_pending(session)
    return ingested


def run_ingestion(
    symbols: list[str] | None = None,
    days: int = 365,
    fixtures: bool = False,
    with_filings: bool = True,
) -> dict[str, int]:
    """Entry point used by the CLI and the scheduler. One transaction per symbol."""
    settings = get_settings()
    symbols = symbols or settings.ingest_symbols.split(",")
    totals = {"prices": 0, "filings": 0}

    for symbol in symbols:
        symbol = symbol.strip().upper()
        try:
            bars = synthetic_prices(symbol) if fixtures else fetch_daily_prices(symbol, days)
            with session_scope() as session:
                totals["prices"] += ingest_prices(session, symbol, bars)
        except Exception:
            log.exception("ingest.prices_failed", symbol=symbol)

    if with_filings:
        try:
            records = (
                load_fixture_filings()
                if fixtures
                else [
                    record
                    for symbol in symbols
                    for record in fetch_recent_filings(symbol.strip().upper())
                ]
            )
            with session_scope() as session:
                totals["filings"] += ingest_filings(session, records)
        except Exception:
            log.exception("ingest.filings_failed")

    # Populate pgvector embeddings when that backend is active (no-op on numpy).
    from filingsdesk.rag.store import get_vector_store

    with session_scope() as session:
        get_vector_store().index_pending(session)

    log.info("ingest.done", **totals)
    return totals
