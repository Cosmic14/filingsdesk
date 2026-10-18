"""API integration tests: real app, real Postgres, in-memory cache."""

import pytest
from fastapi.testclient import TestClient

import filingsdesk.cache.backends as cache_backends
from filingsdesk.api.main import app
from filingsdesk.cache import InMemoryCache
from filingsdesk.ingestion.filings import load_fixture_filings
from filingsdesk.ingestion.prices import synthetic_prices
from filingsdesk.ingestion.service import ingest_filings, ingest_prices


@pytest.fixture
def client(db_session):
    cache_backends._cache = InMemoryCache()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded(db_session):
    ingest_prices(db_session, "AAPL", synthetic_prices("AAPL", days=120))
    ingest_filings(db_session, load_fixture_filings())
    db_session.commit()
    return db_session


def test_health_ok(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_instruments_lists_seeded_symbols(client, seeded):
    response = client.get("/instruments")
    assert response.status_code == 200
    symbols = [row["symbol"] for row in response.json()]
    assert "AAPL" in symbols


def test_prices_returns_ordered_bars(client, seeded):
    body = client.get("/prices/aapl?limit=50").json()
    assert len(body) == 50
    dates = [row["date"] for row in body]
    assert dates == sorted(dates)
    assert all(row["low"] <= row["close"] <= row["high"] for row in body)


def test_prices_unknown_symbol_404(client):
    response = client.get("/prices/ZZZZ")
    assert response.status_code == 404


def test_latest_quote_uses_cache_on_second_call(client, seeded):
    first = client.get("/prices/AAPL/latest").json()
    second = client.get("/prices/AAPL/latest").json()
    assert first["cached"] is False
    assert second["cached"] is True
    assert first["close"] == second["close"]


def test_backtest_returns_metrics_and_curve(client, seeded):
    response = client.post(
        "/backtest",
        json={"symbol": "AAPL", "strategy": "ma_crossover", "params": {"fast": 5, "slow": 20}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["final_equity"] > 0
    assert set(body["metrics"]) >= {"sharpe", "max_drawdown", "total_return", "n_trades"}
    assert len(body["equity_curve"]) == 120


def test_backtest_rejects_unknown_strategy(client, seeded):
    response = client.post("/backtest", json={"symbol": "AAPL", "strategy": "crystal_ball"})
    assert response.status_code == 422


def test_backtest_rejects_bad_params_as_422_not_500(client, seeded):
    response = client.post(
        "/backtest",
        json={"symbol": "AAPL", "strategy": "ma_crossover", "params": {"fast": 50, "slow": 20}},
    )
    assert response.status_code == 422
    assert "fast window" in response.json()["detail"]


def test_backtest_unknown_symbol_404(client):
    response = client.post("/backtest", json={"symbol": "ZZZZ", "strategy": "momentum"})
    assert response.status_code == 404


def test_ask_answers_with_citations(client, seeded):
    response = client.post(
        "/ask", json={"question": "How fast did Apple's Services segment net sales grow?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert "12 percent" in body["answer"]
    assert body["citations"][0]["symbol"] == "AAPL"


def test_ask_refuses_out_of_corpus(client, seeded):
    response = client.post("/ask", json={"question": "Who won the football world cup last year?"})
    body = response.json()
    assert body["refused"] is True
    assert body["citations"] == []


def test_metrics_endpoint_exposes_counters(client, seeded):
    client.get("/prices/AAPL/latest")
    text = client.get("/metrics").text
    assert "filingsdesk_http_requests_total" in text
    assert "filingsdesk_cache_misses_total" in text


class StubAnswerer:
    """Stands in for Claude: quotes the top chunk, or fails like the API would."""

    def __init__(self, fail=False):
        self.fail = fail

    def answer(self, question, chunks):
        from filingsdesk.rag.claude_answerer import AnswererError, Claim, ClaudeResult

        if self.fail:
            raise AnswererError("APITimeoutError: Request timed out.")
        top = chunks[0]
        claim = Claim(text="Summarised by the model.", source=1, quote=top.text[:80])
        return ClaudeResult(True, [(claim, top)], 0, {}, 0.0)


@pytest.fixture
def claude_provider(monkeypatch):
    import filingsdesk.rag.claude_answerer as claude_answerer
    from filingsdesk.config import get_settings

    monkeypatch.setattr(get_settings(), "answer_provider", "claude")
    return lambda answerer: monkeypatch.setattr(claude_answerer, "_answerer", answerer)


def test_ask_with_claude_returns_model_answer_with_citation(client, seeded, claude_provider):
    claude_provider(StubAnswerer())
    body = client.post("/ask", json={"question": "How fast did Apple's Services grow?"}).json()
    assert body["answered_by"] == "claude"
    assert body["answer"] == "Summarised by the model. [1]"
    assert len(body["citations"]) == 1


def test_ask_falls_back_to_extractive_when_claude_fails(client, seeded, claude_provider):
    claude_provider(StubAnswerer(fail=True))
    body = client.post("/ask", json={"question": "How fast did Apple's Services grow?"}).json()
    assert body["answered_by"] == "extractive"
    assert body["refused"] is False and body["citations"]
