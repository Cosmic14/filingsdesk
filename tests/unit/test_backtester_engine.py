"""Engine semantics: hand-computed equity, cost charging, and the look-ahead guard."""

import pandas as pd
import pytest

from filingsdesk.backtester import run_backtest


def make_series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2025-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


def test_equity_curve_hand_computed():
    # returns: [0, +10%, -10%, +10%]; long from bar 1 (signal shifted), 10 bps entry cost
    prices = make_series([100.0, 110.0, 99.0, 108.9])
    signal = make_series([1.0, 1.0, 1.0, 1.0])
    result = run_backtest(prices, signal, cost_bps=10.0, initial_capital=10_000.0)
    expected = [10_000.0, 10_000.0 * 1.099, 10_000.0 * 1.099 * 0.9, 10_000.0 * 1.099 * 0.9 * 1.1]
    assert list(result.equity_curve) == pytest.approx(expected)
    assert result.metrics["final_equity"] == pytest.approx(10_880.1)


def test_signal_on_last_bar_earns_nothing():
    # A strategy that "sees" the final jump the bar it happens must not profit from it.
    prices = make_series([100.0, 100.0, 100.0, 200.0])
    signal = make_series([0.0, 0.0, 0.0, 1.0])
    result = run_backtest(prices, signal, cost_bps=0.0)
    assert result.metrics["final_equity"] == pytest.approx(10_000.0)


def test_signal_day_before_jump_earns_it():
    prices = make_series([100.0, 100.0, 100.0, 200.0])
    signal = make_series([0.0, 0.0, 1.0, 0.0])
    result = run_backtest(prices, signal, cost_bps=0.0)
    assert result.metrics["final_equity"] == pytest.approx(20_000.0)


def test_all_flat_equity_constant():
    prices = make_series([100.0, 120.0, 80.0, 140.0])
    signal = make_series([0.0, 0.0, 0.0, 0.0])
    result = run_backtest(prices, signal, cost_bps=10.0)
    assert (result.equity_curve == 10_000.0).all()
    assert result.metrics["n_trades"] == 0


def test_costs_charged_per_position_change():
    # flat → long → flat: two trades of 10 bps each on flat prices
    prices = make_series([100.0, 100.0, 100.0, 100.0])
    signal = make_series([0.0, 1.0, 0.0, 0.0])
    result = run_backtest(prices, signal, cost_bps=10.0)
    assert result.metrics["n_trades"] == 2
    assert result.metrics["final_equity"] == pytest.approx(10_000.0 * (1 - 0.001) ** 2)


def test_short_position_profits_from_fall():
    prices = make_series([100.0, 100.0, 90.0])
    signal = make_series([0.0, -1.0, -1.0])
    result = run_backtest(prices, signal, cost_bps=0.0)
    assert result.metrics["final_equity"] == pytest.approx(11_000.0)


def test_input_validation():
    prices = make_series([100.0, 101.0])
    with pytest.raises(ValueError, match="same index"):
        run_backtest(prices, make_series([1.0, 1.0, 1.0]))
    with pytest.raises(ValueError, match="strictly positive"):
        run_backtest(make_series([100.0, -1.0]), make_series([0.0, 0.0]))
    with pytest.raises(ValueError, match="within"):
        run_backtest(prices, make_series([2.0, 0.0]))
    with pytest.raises(ValueError, match="cost_bps"):
        run_backtest(prices, make_series([1.0, 1.0]), cost_bps=-1.0)
    with pytest.raises(ValueError, match="empty"):
        run_backtest(make_series([]), make_series([]))
