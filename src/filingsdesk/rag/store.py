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
from filingsdesk.db import FilingChunk, get_engine
from filingsdesk.rag.embeddings import get_embedder

log = structlog.get_logger(__name__)


class VectorStore(Protocol):
    def index_pending(self, session: Session) -> int: ...

    def search(self, session: Session, query: str, top_k: int) -> list[tuple[int, float]]: ...


class NumpyVectorStore:
    """Embeds the chunk corpus in memory; refreshes when the corpus changes."""

    def __init__(self) -> None:
        self._chunk_ids: list[int] = []
        self._matrix: np.ndarray | None = None
        self._corpus_key: tuple[int, int] | None = None

    def index_pending(self, session: Session) -> int:
        return 0  # nothing persisted; embedding happens lazily at query time

    def _refresh(self, session: Session) -> None:
        rows = session.execute(
            select(FilingChunk.id, FilingChunk.text).order_by(FilingChunk.id)
        ).all()
        key = (len(rows), rows[-1][0] if rows else 0)
        if key == self._corpus_key:
            return
        self._chunk_ids = [row[0] for row in rows]
        texts = [row[1] for row in rows]
        self._matrix = get_embedder().embed(texts) if texts else None
        self._corpus_key = key
        log.info("vectorstore.numpy_refreshed", chunks=len(rows))

    def search(self, session: Session, query: str, top_k: int) -> list[tuple[int, float]]:
        self._refresh(session)
        if self._matrix is None:
            return []
        query_vec = get_embedder().embed([query])[0]
        similarities = self._matrix @ query_vec
        order = np.argsort(-similarities)[:top_k]
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

    def search(self, session: Session, query: str, top_k: int) -> list[tuple[int, float]]:
        query_vec = get_embedder().embed([query])[0]
        rows = session.execute(
            text(
                "SELECT id, 1 - (embedding <=> :vec) AS similarity FROM filing_chunks "
                "WHERE embedding IS NOT NULL ORDER BY embedding <=> :vec LIMIT :k"
            ),
            {"vec": str(query_vec.tolist()), "k": top_k},
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
