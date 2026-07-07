"""Metric maths validated against hand-computed values."""

import numpy as np
import pandas as pd
import pytest

from filingsdesk.backtester.metrics import (
    annualised_sharpe,
    annualised_volatility,
    cagr,
    max_drawdown,
    total_return,
)


def test_sharpe_hand_computed():
    # mean = 0.02, sample std = 0.01 → sharpe = 2 * sqrt(252)
    returns = pd.Series([0.01, 0.02, 0.03])
    assert annualised_sharpe(returns) == pytest.approx(2 * np.sqrt(252))


def test_sharpe_with_risk_free_rate():
    # excess = [0.00, 0.01, 0.02]: mean = 0.01, std = 0.01 → sharpe = sqrt(252)
    returns = pd.Series([0.01, 0.02, 0.03])
    assert annualised_sharpe(returns, risk_free_daily=0.01) == pytest.approx(np.sqrt(252))


def test_sharpe_degenerate_cases_return_zero():
    assert annualised_sharpe(pd.Series([0.01])) == 0.0
    assert annualised_sharpe(pd.Series([0.01, 0.01, 0.01])) == 0.0  # zero variance
    assert annualised_sharpe(pd.Series([], dtype=float)) == 0.0


def test_max_drawdown_hand_computed():
    # peak 120 → trough 80: dd = 1 - 80/120 = 1/3
    equity = pd.Series([100.0, 120.0, 90.0, 100.0, 80.0])
    assert max_drawdown(equity) == pytest.approx(1 / 3)


def test_max_drawdown_monotonic_rise_is_zero():
    assert max_drawdown(pd.Series([100.0, 101.0, 105.0])) == 0.0


def test_total_return_hand_computed():
    assert total_return(pd.Series([100.0, 150.0])) == pytest.approx(0.5)


def test_cagr_one_year_doubling():
    # 253 points = 252 trading-day gaps = exactly one year → CAGR equals total return
    equity = pd.Series(np.linspace(100, 200, 253))
    assert cagr(equity) == pytest.approx(1.0)


def test_volatility_hand_computed():
    returns = pd.Series([0.01, 0.03])  # std (ddof=1) = 0.0141421...
    expected = returns.std(ddof=1) * np.sqrt(252)
    assert annualised_volatility(returns) == pytest.approx(float(expected))
