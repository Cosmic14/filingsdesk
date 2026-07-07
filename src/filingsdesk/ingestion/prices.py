"""Daily price bars: live via yfinance (retried), or deterministic synthetic fixtures.

Fixture bars are a seeded geometric random walk — clearly synthetic, used so that the
demo, tests, and CI never depend on an external market-data API.
"""

import datetime as dt
from dataclasses import dataclass

import numpy as np
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

log = structlog.get_logger(__name__)

FIXTURE_ANCHOR_DATE = dt.date(2026, 7, 3)  # fixed so fixture data is deterministic


@dataclass(frozen=True)
class PriceBar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=1, max=20),
    reraise=True,
)
def fetch_daily_prices(symbol: str, days: int = 365) -> list[PriceBar]:
    """Fetch daily OHLCV from yfinance with exponential-backoff retries."""
    import yfinance as yf

    log.info("prices.fetch", symbol=symbol, days=days)
    frame = yf.Ticker(symbol).history(period=f"{days}d", interval="1d", auto_adjust=True)
    bars = [
        PriceBar(
            date=index.date(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(row["Volume"]),
        )
        for index, row in frame.iterrows()
    ]
    log.info("prices.fetched", symbol=symbol, bars=len(bars))
    return bars


def synthetic_prices(symbol: str, days: int = 500) -> list[PriceBar]:
    """Deterministic per-symbol random walk (same symbol → same series, every run)."""
    seed = abs(hash_symbol(symbol)) % 2**32
    rng = np.random.RandomState(seed)

    dates = business_days_ending(FIXTURE_ANCHOR_DATE, days)
    daily_returns = rng.normal(loc=0.0004, scale=0.018, size=days)
    closes = 100.0 * np.exp(np.cumsum(daily_returns))
    spreads = np.abs(rng.normal(0.0, 0.008, size=days))

    bars = []
    prev_close = float(closes[0])
    for i, date in enumerate(dates):
        close = float(closes[i])
        open_ = prev_close
        high = max(open_, close) * (1 + float(spreads[i]))
        low = min(open_, close) * (1 - float(spreads[i]))
        bars.append(
            PriceBar(
                date=date,
                open=round(open_, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=int(rng.randint(1_000_000, 80_000_000)),
            )
        )
        prev_close = close
    return bars


def hash_symbol(symbol: str) -> int:
    """Stable across processes (unlike builtin hash(), which is salted)."""
    value = 0
    for ch in symbol.upper():
        value = (value * 131 + ord(ch)) % 2**31
    return value


def business_days_ending(end: dt.date, count: int) -> list[dt.date]:
    days: list[dt.date] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= dt.timedelta(days=1)
    return list(reversed(days))
