"""FastAPI application: typed routes, request logging, Prometheus, health."""

import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from filingsdesk import __version__
from filingsdesk.api.metrics import REQUEST_COUNT, REQUEST_LATENCY
from filingsdesk.api.routes import ask, backtest, instruments, prices
from filingsdesk.db import get_engine
from filingsdesk.logging_setup import configure_logging

log = structlog.get_logger("filingsdesk.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    yield


app = FastAPI(
    title="FilingsDesk",
    version=__version__,
    description="Market data, backtesting, and citation-grounded Q&A over SEC filings.",
    lifespan=lifespan,
)
app.include_router(instruments.router)
app.include_router(prices.router)
app.include_router(backtest.router)
app.include_router(ask.router)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start

    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)  # template, not raw path
    REQUEST_COUNT.labels(request.method, route_path, response.status_code).inc()
    REQUEST_LATENCY.labels(request.method, route_path).observe(elapsed)
    log.info(
        "http.request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(elapsed * 1000, 2),
    )
    return response


@app.get("/health", tags=["ops"])
def health() -> dict:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    status = "ok" if database == "ok" else "degraded"
    return {"status": status, "database": database, "version": __version__}


@app.get("/metrics", tags=["ops"])
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
