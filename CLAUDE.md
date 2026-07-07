# FilingsDesk — project conventions

Market intelligence platform: ingestion (yfinance + SEC EDGAR) → Postgres → Redis cache →
FastAPI → vectorised backtester → RAG Q&A over filings with a CI eval harness → Streamlit dashboard.

## Stack
Python 3.12 · FastAPI · SQLAlchemy 2 + Alembic · Postgres 16 (+pgvector) · Redis ·
pandas/NumPy · structlog · pytest + Hypothesis · ruff · Docker Compose · GitHub Actions.

## Layout
- `src/filingsdesk/` — application code (`db`, `cache`, `ingestion`, `backtester`, `rag`, `api`, `dashboard`)
- `tests/` — `unit/`, `integration/` (needs Postgres; marked `integration`), `property/`
- `docs/adr/` — one ADR per significant decision, written BEFORE the component
- `evals/` — RAG eval dataset (`dataset.jsonl`); runner is `filingsdesk-evals`
- `data/fixtures/` — offline sample prices + filings so everything runs without network

## Commands
- Test (fast): `pytest -m "not integration"`
- Test (all, needs local Postgres): `pytest`
- Coverage: `pytest --cov`
- Lint: `ruff check . && ruff format --check .`
- Migrate: `alembic upgrade head`
- API: `uvicorn filingsdesk.api.main:app --reload`
- Ingest fixtures (offline): `filingsdesk-ingest --fixtures`
- Evals: `filingsdesk-evals --dataset evals/dataset.jsonl`
- Dashboard: `streamlit run src/filingsdesk/dashboard/app.py`

## Working rules (non-negotiable)
1. Small conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`).
2. ADR in `docs/adr/` before each new component.
3. The owner must be able to explain every feature — end sessions with a 5-question quiz.
4. Test-first where it matters; ~80% coverage on core modules (backtester, rag, cache, ingestion).
5. If behind, scope-cut from the top: dashboard polish → agentic stretch → benchmarks → 2nd strategy.
   Never cut: tests, README, evals, deployment.

## Environment notes
- Local dev on macOS: Postgres 16 via Homebrew (unix socket, no password). No local Redis or
  pgvector — the code degrades gracefully (in-memory cache, numpy vector store). CI and
  docker-compose run the full stack (pgvector/pgvector:pg16 + redis:7).
- Config via env vars / `.env` (see `filingsdesk/config.py`). Never commit secrets.
