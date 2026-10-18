"""Vector stores (ADR-0004): pgvector when the extension is present, numpy otherwise.

Both return the same shape: (chunk_id, cosine_similarity) pairs, best first. The numpy
store is exact O(n) search and doubles as the oracle for the pgvector path in tests.
"""

from typing import Protocol

import numpy as np
import structlog
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from filingsdesk.config import get_settings
from filingsdesk.db import Filing, FilingChunk, Instrument, get_engine
from filingsdesk.rag.embeddings import embed_query, get_embedder

log = structlog.get_logger(__name__)


class VectorStore(Protocol):
    def index_pending(self, session: Session) -> int: ...

    def search(
        self,
        session: Session,
        query: str,
        top_k: int,
        symbols: list[str] | None = None,
        keyword_query: str | None = None,
    ) -> list[tuple[int, float]]: ...


class NumpyVectorStore:
    """Embeds the chunk corpus in memory; refreshes when the corpus changes."""

    def __init__(self) -> None:
        self._chunk_ids: list[int] = []
        self._symbols: list[str | None] = []
        self._matrix: np.ndarray | None = None
        self._corpus_key: tuple[int, int] | None = None

    def index_pending(self, session: Session) -> int:
        return 0  # nothing persisted; embedding happens lazily at query time

    def _refresh(self, session: Session) -> None:
        rows = session.execute(
            select(FilingChunk.id, FilingChunk.text, Instrument.symbol)
            .join(Filing, FilingChunk.filing_id == Filing.id)
            .outerjoin(Instrument, Filing.instrument_id == Instrument.id)
            .order_by(FilingChunk.id)
        ).all()
        key = (len(rows), rows[-1][0] if rows else 0)
        if key == self._corpus_key:
            return
        self._chunk_ids = [row[0] for row in rows]
        self._symbols = [row[2] for row in rows]
        texts = [row[1] for row in rows]
        self._matrix = get_embedder().embed(texts) if texts else None
        self._corpus_key = key
        log.info("vectorstore.numpy_refreshed", chunks=len(rows))

    def search(
        self,
        session: Session,
        query: str,
        top_k: int,
        symbols: list[str] | None = None,
        keyword_query: str | None = None,  # dense-only store
    ) -> list[tuple[int, float]]:
        self._refresh(session)
        if self._matrix is None:
            return []
        query_vec = embed_query(query)
        similarities = self._matrix @ query_vec
        if symbols:
            allowed = np.array([s in symbols for s in self._symbols])
            similarities = np.where(allowed, similarities, -np.inf)
        order = [i for i in np.argsort(-similarities)[:top_k] if np.isfinite(similarities[i])]
        return [(self._chunk_ids[i], float(similarities[i])) for i in order]


class PgVectorStore:
    """Persists embeddings in `filing_chunks.embedding`, searches with `<=>` (cosine)."""

    def index_pending(self, session: Session) -> int:
        rows = session.execute(
            text("SELECT id, text FROM filing_chunks WHERE embedding IS NULL ORDER BY id")
        ).all()
        if not rows:
            return 0
        embeddings = get_embedder().embed([row[1] for row in rows])
        for (chunk_id, _), vector in zip(rows, embeddings, strict=True):
            session.execute(
                text("UPDATE filing_chunks SET embedding = :vec WHERE id = :id"),
                {"vec": str(vector.tolist()), "id": chunk_id},
            )
        log.info("vectorstore.pgvector_indexed", chunks=len(rows))
        return len(rows)

    def search(
        self,
        session: Session,
        query: str,
        top_k: int,
        symbols: list[str] | None = None,
        keyword_query: str | None = None,
    ) -> list[tuple[int, float]]:
        """Hybrid: dense cosine and full-text keyword rankings merged with reciprocal rank
        fusion (k=60). Returns (chunk_id, cosine similarity), best fused rank first."""
        query_vec = embed_query(query)
        company_filter = (
            "AND c.filing_id IN (SELECT f.id FROM filings f JOIN instruments i "
            "ON i.id = f.instrument_id WHERE i.symbol = ANY(:symbols)) "
            if symbols
            else ""
        )
        # OR the query terms: an AND of every word would miss most relevant chunks.
        rows = session.execute(
            text(
                f"""
                WITH q AS (
                    SELECT NULLIF(replace(plainto_tsquery('english', :query)::text, '&', '|'), '')
                           ::tsquery AS tsq
                ),
                dense AS (
                    SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> :vec) AS r
                    FROM filing_chunks c
                    WHERE c.embedding IS NOT NULL {company_filter}
                    ORDER BY c.embedding <=> :vec LIMIT :pool
                ),
                sparse AS (
                    SELECT c.id,
                           row_number() OVER (ORDER BY ts_rank_cd(c.search_tsv, q.tsq) DESC) AS r
                    FROM filing_chunks c, q
                    WHERE q.tsq IS NOT NULL AND c.search_tsv @@ q.tsq {company_filter}
                    ORDER BY ts_rank_cd(c.search_tsv, q.tsq) DESC LIMIT :pool
                ),
                fused AS (
                    SELECT id, sum(1.0 / (60 + r)) AS score
                    FROM (SELECT * FROM dense UNION ALL SELECT * FROM sparse) ranked
                    GROUP BY id
                )
                SELECT c.id, 1 - (c.embedding <=> :vec) AS similarity
                FROM fused JOIN filing_chunks c ON c.id = fused.id
                WHERE c.embedding IS NOT NULL
                ORDER BY fused.score DESC LIMIT :k
                """
            ),
            {
                "vec": str(query_vec.tolist()),
                "query": keyword_query or query,
                "k": top_k,
                "pool": top_k * 4,
                "symbols": symbols or [],
            },
        ).all()
        return [(row[0], float(row[1])) for row in rows]


_store: VectorStore | None = None


def _embedding_column_exists() -> bool:
    columns = inspect(get_engine()).get_columns("filing_chunks")
    return any(column["name"] == "embedding" for column in columns)


def get_vector_store() -> VectorStore:
    """Backend per config: 'auto' picks pgvector iff the embedding column exists."""
    global _store
    if _store is None:
        backend = get_settings().vector_backend
        if backend == "auto":
            backend = "pgvector" if _embedding_column_exists() else "numpy"
        _store = PgVectorStore() if backend == "pgvector" else NumpyVectorStore()
        log.info("vectorstore.backend", backend=backend)
    return _store
