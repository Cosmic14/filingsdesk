"""Synthetic fixture bars: determinism and OHLC consistency."""

from filingsdesk.ingestion.prices import business_days_ending, synthetic_prices


def test_synthetic_prices_deterministic():
    a = synthetic_prices("AAPL", days=50)
    b = synthetic_prices("AAPL", days=50)
    assert a == b


def test_synthetic_prices_differ_per_symbol():
    assert synthetic_prices("AAPL", days=50) != synthetic_prices("MSFT", days=50)


def test_ohlc_invariants():
    for bar in synthetic_prices("NVDA", days=200):
        assert bar.low <= min(bar.open, bar.close)
        assert bar.high >= max(bar.open, bar.close)
        assert bar.low > 0
        assert bar.volume > 0


def test_dates_are_business_days_ascending():
    bars = synthetic_prices("AMZN", days=100)
    dates = [bar.date for bar in bars]
    assert dates == sorted(dates)
    assert len(set(dates)) == 100
    assert all(d.weekday() < 5 for d in dates)


def test_business_days_ending_skips_weekends():
    import datetime as dt

    days = business_days_ending(dt.date(2026, 7, 6), 3)  # Monday
    assert days == [dt.date(2026, 7, 2), dt.date(2026, 7, 3), dt.date(2026, 7, 6)]
