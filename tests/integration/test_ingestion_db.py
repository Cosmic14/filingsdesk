"""Idempotency against real Postgres: re-running ingestion converges, never duplicates."""

import dataclasses

from sqlalchemy import func, select

from filingsdesk.db import Filing, FilingChunk, Instrument, Price
from filingsdesk.ingestion.filings import load_fixture_filings
from filingsdesk.ingestion.prices import synthetic_prices
from filingsdesk.ingestion.service import ingest_filings, ingest_prices, upsert_instrument


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_price_upsert_is_idempotent(db_session):
    bars = synthetic_prices("AAPL", days=30)
    ingest_prices(db_session, "AAPL", bars)
    db_session.commit()
    assert count(db_session, Price) == 30

    ingest_prices(db_session, "AAPL", bars)  # crash-recovery re-run
    db_session.commit()
    assert count(db_session, Price) == 30
    assert count(db_session, Instrument) == 1


def test_price_upsert_updates_conflicting_rows(db_session):
    bars = synthetic_prices("MSFT", days=5)
    ingest_prices(db_session, "MSFT", bars)
    db_session.commit()

    revised = [dataclasses.replace(bars[-1], close=999.99)]
    ingest_prices(db_session, "MSFT", revised)
    db_session.commit()

    stored = db_session.scalars(select(Price).order_by(Price.date.desc())).first()
    assert stored.close == 999.99
    assert count(db_session, Price) == 5


def test_filing_ingest_chunks_and_is_idempotent(db_session):
    records = load_fixture_filings()
    assert ingest_filings(db_session, records) == 5
    db_session.commit()
    chunk_count = count(db_session, FilingChunk)
    assert count(db_session, Filing) == 5
    assert chunk_count >= 15  # every fixture splits into multiple section chunks

    assert ingest_filings(db_session, records) == 0  # re-run inserts nothing
    db_session.commit()
    assert count(db_session, Filing) == 5
    assert count(db_session, FilingChunk) == chunk_count


def test_chunks_carry_section_labels(db_session):
    ingest_filings(db_session, load_fixture_filings()[:1])
    db_session.commit()
    sections = set(db_session.scalars(select(FilingChunk.section)).all())
    assert any(s and s.startswith("ITEM 1A.") for s in sections)


def test_upsert_instrument_race_safe(db_session):
    first = upsert_instrument(db_session, "nvda")
    second = upsert_instrument(db_session, "NVDA")
    assert first.id == second.id
    assert first.symbol == "NVDA"
