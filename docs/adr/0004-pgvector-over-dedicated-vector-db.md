# ADR-0004: pgvector over a dedicated vector DB, with a numpy fallback

**Status:** accepted · 2026-07-07

## Problem
The RAG layer needs nearest-neighbour search over filing-chunk embeddings. Where do the
vectors live?

## Options
1. **pgvector** — vectors live next to the rows they describe; one database, one backup
   story, joins between chunks and filings are plain SQL.
2. Dedicated vector DB (Qdrant/Weaviate/Pinecone) — better at 10⁸+ vectors, but adds a
   service, a sync problem (two sources of truth), and ops surface for a corpus of
   thousands of chunks.
3. FAISS/numpy in-process — no persistence/ops story on its own, but trivially simple.

## Decision
pgvector as the primary store (`filing_chunks.embedding vector(384)`, cosine distance,
HNSW index). This is also one more reason Postgres won ADR-0001.

**Fallback:** local dev machines may lack the extension (it isn't bundled with Homebrew
Postgres 16). The Alembic migration checks `pg_available_extensions` and skips the vector
column when absent; the column is left unmapped in the ORM (the pgvector store reads and
writes it via SQL), so application code never depends on its existence.
A `NumpyVectorStore` then serves retrieval by embedding chunks in memory.
Backend selection is automatic with an env override (`VECTOR_BACKEND=pgvector|numpy`).
CI and docker-compose run the real thing via the `pgvector/pgvector:pg16` image, so the
pgvector path is exercised on every push.

## Trade-offs
The conditional migration means a local schema can lack one column — contained by the
deferred ORM mapping and documented here. The numpy path is O(n) exact search — fine for
this corpus, and it doubles as the ground-truth oracle in tests for the pgvector path.
