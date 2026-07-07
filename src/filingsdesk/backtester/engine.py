"""Vectorised backtest engine (ADR-0003).

The no-look-ahead guarantee lives in exactly one line here: a signal computed on bar t
is shifted to earn the return of bar t+1 (`signal.shift(1)`). Transaction costs are
charged in basis points on every change in position, including the entry trade.
"""

from dataclasses import dataclass, field

import pandas as pd

from filingsdesk.backtester import metrics as m


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    net_returns: pd.Series
    positions: pd.Series
    metrics: dict[str, float] = field(default_factory=dict)


def run_backtest(
    prices: pd.Series,
    signal: pd.Series,
    cost_bps: float = 10.0,
    initial_capital: float = 10_000.0,
) -> BacktestResult:
    """Simulate holding `signal`-directed positions in a single instrument.

    prices: close series indexed by date (strictly positive).
    signal: target position per bar in [-1, +1], same index as prices.
    cost_bps: one-way transaction cost in basis points of traded notional.
    """
    if not prices.index.equals(signal.index):
        raise ValueError("prices and signal must share the same index")
    if len(prices) == 0:
        raise ValueError("empty price series")
    if (prices <= 0).any():
        raise ValueError("prices must be strictly positive")
    if (signal.abs() > 1).any():
        raise ValueError("signal must be within [-1, +1]")
    if cost_bps < 0:
        raise ValueError("cost_bps must be >= 0")

    # The look-ahead guard: today's signal earns tomorrow's return.
    positions = signal.shift(1).fillna(0.0)

    asset_returns = prices.pct_change().fillna(0.0)
    gross_returns = positions * asset_returns

    # |Δposition| in units of exposure; first bar's trade is the position itself.
    turnover = positions.diff()
    turnover.iloc[0] = positions.iloc[0]
    cost_returns = turnover.abs() * (cost_bps / 10_000.0)

    net_returns = gross_returns - cost_returns
    equity_curve = initial_capital * (1.0 + net_returns).cumprod()

    result_metrics = {
        "total_return": m.total_return(equity_curve),
        "cagr": m.cagr(equity_curve),
        "sharpe": m.annualised_sharpe(net_returns),
        "max_drawdown": m.max_drawdown(equity_curve),
        "volatility": m.annualised_volatility(net_returns),
        "n_trades": int((turnover.abs() > 0).sum()),
        "final_equity": float(equity_curve.iloc[-1]),
    }
    return BacktestResult(
        equity_curve=equity_curve,
        net_returns=net_returns,
        positions=positions,
        metrics=result_metrics,
    )
