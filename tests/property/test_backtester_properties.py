"""Property-based invariants of the engine (Hypothesis).

Price moves are bounded (values in [10, 1000] → worst single-bar return -99%), which is
what guarantees positivity for long/flat portfolios: a real long position cannot lose
more than 100%, and 10 bps of costs cannot push a -99% bar past -100%.
"""

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from filingsdesk.backtester import ma_crossover, run_backtest

prices_strategy = st.lists(
    st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    min_size=2,
    max_size=60,
)


def to_series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2025-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


@given(values=prices_strategy, signal_bits=st.lists(st.booleans(), min_size=60, max_size=60))
@settings(deadline=None)
def test_long_flat_equity_always_positive(values, signal_bits):
    prices = to_series(values)
    signal = pd.Series([1.0 if b else 0.0 for b in signal_bits[: len(values)]], index=prices.index)
    result = run_backtest(prices, signal, cost_bps=10.0)
    assert (result.equity_curve > 0).all()


@given(values=prices_strategy)
@settings(deadline=None)
def test_flat_strategy_preserves_capital(values):
    prices = to_series(values)
    signal = pd.Series(0.0, index=prices.index)
    result = run_backtest(prices, signal, cost_bps=10.0)
    assert (result.equity_curve == 10_000.0).all()


@given(values=prices_strategy, signal_bits=st.lists(st.booleans(), min_size=60, max_size=60))
@settings(deadline=None)
def test_higher_costs_never_help(values, signal_bits):
    prices = to_series(values)
    signal = pd.Series([1.0 if b else 0.0 for b in signal_bits[: len(values)]], index=prices.index)
    cheap = run_backtest(prices, signal, cost_bps=0.0)
    dear = run_backtest(prices, signal, cost_bps=50.0)
    assert dear.metrics["final_equity"] <= cheap.metrics["final_equity"] + 1e-9


@given(
    values=st.lists(
        st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=6,
        max_size=60,
    )
)
@settings(deadline=None)
def test_future_bars_cannot_change_the_past(values):
    """Causality end-to-end: strategy + engine output for bar t is invariant to bar t+1."""
    full = to_series(values)
    truncated = full.iloc[:-1]
    result_full = run_backtest(full, ma_crossover(full, fast=2, slow=3), cost_bps=10.0)
    result_trunc = run_backtest(truncated, ma_crossover(truncated, fast=2, slow=3), cost_bps=10.0)
    pd.testing.assert_series_equal(
        result_full.equity_curve.iloc[:-1], result_trunc.equity_curve, check_exact=False
    )
