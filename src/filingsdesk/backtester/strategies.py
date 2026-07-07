"""Strategies are pure functions: close-price series → target position in {-1, 0, +1}.

They may look at data up to and including bar t to decide the position *requested* at
bar t; the engine shifts that request by one bar before any P&L is earned (ADR-0003),
so strategies cannot introduce look-ahead bias even if they try.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd

Strategy = Callable[..., pd.Series]


def ma_crossover(prices: pd.Series, fast: int = 20, slow: int = 50) -> pd.Series:
    """Long when the fast moving average is above the slow one, flat otherwise.

    Signal is 0 (not NaN) until the slow window is full — an unwarmed strategy
    holds no position rather than an undefined one.
    """
    if fast >= slow:
        raise ValueError(f"fast window ({fast}) must be smaller than slow window ({slow})")
    fast_ma = prices.rolling(fast).mean()
    slow_ma = prices.rolling(slow).mean()
    signal = (fast_ma > slow_ma).astype(float)
    signal[slow_ma.isna()] = 0.0
    return signal


def momentum(prices: pd.Series, lookback: int = 63) -> pd.Series:
    """Sign of the trailing `lookback`-bar return: long winners, short losers.

    Flat while the lookback window is unwarmed or the trailing return is exactly zero.
    """
    if lookback < 1:
        raise ValueError(f"lookback must be >= 1, got {lookback}")
    trailing = prices.pct_change(lookback)
    signal = pd.Series(np.sign(trailing.to_numpy()), index=prices.index)
    return signal.fillna(0.0)


STRATEGIES: dict[str, Strategy] = {
    "ma_crossover": ma_crossover,
    "momentum": momentum,
}
