# Deploying FilingsDesk

## Local (one command)

```bash
docker compose up --build
```

Brings up Postgres (with pgvector), Redis, the API (auto-migrates), the ingestion worker
(seeds deterministic fixture data on startup), and the dashboard:
API → http://localhost:8000/docs · dashboard → http://localhost:8501

## Fly.io (free tier)

```bash
fly launch --no-deploy          # uses the checked-in fly.toml
fly postgres create --name filingsdesk-db
fly postgres attach filingsdesk-db      # sets DATABASE_URL secret
fly redis create                        # Upstash Redis; set REDIS_URL from output
fly secrets set REDIS_URL=<url>
fly deploy                              # release_command runs alembic upgrade head
fly ssh console -C "filingsdesk-ingest --fixtures"   # seed demo data
```

Notes:
- The Fly Postgres image ships pgvector; the conditional migration enables it
  automatically, and the app falls back to the numpy store if it ever isn't there.
- Streamlit dashboard can be deployed as a second Fly app from the `dashboard` build
  target with `FILINGSDESK_API_URL` pointed at the API app URL, or on Streamlit
  Community Cloud for free.

## Images

CI pushes `ghcr.io/<owner>/<repo>/api:latest` and `.../ingestion:latest` on every merge
to main (see `.github/workflows/ci.yml`).
