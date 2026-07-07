"""Performance metrics. Pure functions over return/equity series."""

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def annualised_sharpe(
    returns: pd.Series, risk_free_daily: float = 0.0, periods: int = TRADING_DAYS_PER_YEAR
) -> float:
    """Sharpe = mean excess return / stddev (sample, ddof=1), annualised by √periods.

    Returns 0.0 for degenerate series (fewer than 2 points or zero variance) rather
    than propagating NaN/inf into API responses.
    """
    excess = returns - risk_free_daily
    if len(excess) < 2:
        return 0.0
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    return float(excess.mean() / std * np.sqrt(periods))


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough decline, as a positive fraction (0.25 = -25%)."""
    if len(equity) == 0:
        return 0.0
    running_peak = equity.cummax()
    drawdown = 1.0 - equity / running_peak
    return float(drawdown.max())


def total_return(equity: pd.Series) -> float:
    if len(equity) < 2 or equity.iloc[0] == 0:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def cagr(equity: pd.Series, periods: int = TRADING_DAYS_PER_YEAR) -> float:
    if len(equity) < 2 or equity.iloc[0] <= 0 or equity.iloc[-1] <= 0:
        return 0.0
    years = (len(equity) - 1) / periods
    # Log space: annualising a large move over a tiny fraction of a year overflows the
    # naive power form. Non-finite results (absurd annualisations) are reported as 0.
    with np.errstate(over="ignore"):
        value = np.expm1(np.log(equity.iloc[-1] / equity.iloc[0]) / years)
    return float(value) if np.isfinite(value) else 0.0


def annualised_volatility(returns: pd.Series, periods: int = TRADING_DAYS_PER_YEAR) -> float:
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(periods))
