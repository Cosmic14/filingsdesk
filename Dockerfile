# Multi-stage: wheels built once, runtime images stay free of build tooling.

FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[dashboard]"

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels filingsdesk[dashboard] \
    && rm -rf /wheels
# Source tree kept for alembic (script_location) and bundled fixtures/evals.
COPY alembic.ini ./
COPY src ./src
COPY data ./data
COPY evals ./evals

FROM base AS api
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn filingsdesk.api.main:app --host 0.0.0.0 --port 8000"]

FROM base AS ingestion
CMD ["python", "-m", "filingsdesk.ingestion.scheduler"]

FROM base AS dashboard
EXPOSE 8501
CMD ["streamlit", "run", "src/filingsdesk/dashboard/app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
