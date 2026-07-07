# ADR-0001: Postgres over SQLite

**Status:** accepted · 2026-07-07

## Problem
We need a primary store for instruments, prices, and filings that supports concurrent
writers (ingestion) and readers (API), real indexes, and — later — vector search.

## Options
1. **SQLite** — zero-ops, single file. But single-writer, no server, no pgvector, and it
   signals "notebook project" rather than "system".
2. **Postgres** — real concurrency, rich indexing, `INSERT … ON CONFLICT` for idempotent
   upserts, pgvector for the RAG layer, first-class Alembic/SQLAlchemy support.
3. Managed NoSQL (Dynamo/Mongo) — wrong shape; the data is relational (instruments 1→N
   prices/filings) and query patterns are range scans over indexed keys.

## Decision
Postgres 16. One store serves both relational and vector workloads (see ADR-0004), which
keeps the stack small and the deployment one `docker compose up`.

## Trade-offs
Postgres needs a running server locally (Homebrew service / Docker) — accepted; the
compose file makes it one command. SQLite would have made tests lighter, but integration
tests against real Postgres catch dialect-specific behaviour (`ON CONFLICT`, indexes) that
SQLite would mask.
