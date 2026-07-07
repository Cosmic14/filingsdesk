"""Strategy signal correctness on small hand-checked series."""

import pandas as pd
import pytest

from filingsdesk.backtester import ma_crossover, momentum


def make_series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2025-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


def test_ma_crossover_hand_checked():
    prices = make_series([10, 11, 12, 11, 10, 9])
    # fast(2): [-, 10.5, 11.5, 11.5, 10.5, 9.5]; slow(3): [-, -, 11, 11.33, 11, 10]
    signal = ma_crossover(prices, fast=2, slow=3)
    assert list(signal) == [0.0, 0.0, 1.0, 1.0, 0.0, 0.0]


def test_ma_crossover_flat_during_warmup():
    prices = make_series(list(range(1, 60)))
    signal = ma_crossover(prices, fast=20, slow=50)
    assert (signal.iloc[:49] == 0.0).all()  # slow window unwarmed → hold nothing
    assert signal.iloc[49:].isin([0.0, 1.0]).all()


def test_ma_crossover_rejects_bad_windows():
    with pytest.raises(ValueError, match="fast window"):
        ma_crossover(make_series([1, 2, 3]), fast=50, slow=20)


def test_momentum_hand_checked():
    prices = make_series([100.0, 101.0, 101.0, 100.0])
    signal = momentum(prices, lookback=1)
    assert list(signal) == [0.0, 1.0, 0.0, -1.0]


def test_momentum_rejects_bad_lookback():
    with pytest.raises(ValueError, match="lookback"):
        momentum(make_series([1.0, 2.0]), lookback=0)
