"""Retrieval: vector search + hydration with citation metadata (filing, section)."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from filingsdesk.db import Filing, FilingChunk, Instrument
from filingsdesk.rag.guardrails import screen_for_injection
from filingsdesk.rag.store import get_vector_store


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    filing_id: int
    accession_no: str
    symbol: str | None
    form_type: str
    section: str | None
    text: str
    similarity: float
    injection_flags: tuple[str, ...] = ()


def retrieve(session: Session, question: str, top_k: int = 5) -> list[RetrievedChunk]:
    hits = get_vector_store().search(session, question, top_k)
    if not hits:
        return []
    by_id = dict(hits)
    rows = session.execute(
        select(FilingChunk, Filing, Instrument.symbol)
        .join(Filing, FilingChunk.filing_id == Filing.id)
        .outerjoin(Instrument, Filing.instrument_id == Instrument.id)
        .where(FilingChunk.id.in_(by_id))
    ).all()
    results = [
        RetrievedChunk(
            chunk_id=chunk.id,
            filing_id=filing.id,
            accession_no=filing.accession_no,
            symbol=symbol,
            form_type=filing.form_type,
            section=chunk.section,
            text=chunk.text,
            similarity=by_id[chunk.id],
            injection_flags=tuple(screen_for_injection(chunk.text)),
        )
        for chunk, filing, symbol in rows
    ]
    return sorted(results, key=lambda r: -r.similarity)
