"""Тесты структуры рынка (пивоты/ADX) и Фибоначчи — на синтетике, без сети."""

from __future__ import annotations

import pandas as pd

from tis.analysis.fibonacci import FibonacciAnalysis, calculate_fibonacci
from tis.analysis.market_structure import (
    calculate_adx,
    find_pivot_highs,
    find_pivot_lows,
)


def _ohlc(closes: list[float], spread: float = 0.5) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "open_time": pd.date_range("2024-01-01", periods=n, freq="h"),
        "open": closes,
        "high": [c + spread for c in closes],
        "low": [c - spread for c in closes],
        "close": closes,
        "volume": [1000.0] * n,
    })


def _zigzag(n: int = 60) -> pd.DataFrame:
    vals = []
    for i in range(n):
        p = i % 10
        vals.append(90 + 4 * p if p <= 5 else 110 - 4 * (p - 5))
    return _ohlc([float(v) for v in vals])


class TestPivots:
    def test_pivot_highs_near_peaks(self):
        highs = find_pivot_highs(_zigzag(), window=4)
        assert highs and max(highs) > 105  # пики ~110

    def test_pivot_lows_near_troughs(self):
        lows = find_pivot_lows(_zigzag(), window=4)
        assert lows and min(lows) < 95  # впадины ~90

    def test_flat_series_no_pivots(self):
        df = _ohlc([100.0] * 40)
        # на абсолютно плоском ряде выраженных пивотов быть не должно
        assert find_pivot_highs(df) == [] or all(abs(h - 100) < 1 for h in find_pivot_highs(df))


class TestAdx:
    def test_in_valid_range(self):
        adx = calculate_adx(_zigzag())
        assert isinstance(adx, float)
        assert 0 <= adx <= 100


class TestFibonacci:
    def test_returns_analysis_with_levels(self):
        df = _zigzag()
        price = float(df["close"].iloc[-1])
        fib = calculate_fibonacci(df, price)
        assert isinstance(fib, FibonacciAnalysis)
        assert fib.levels  # уровни рассчитаны
        assert fib.swing_high > fib.swing_low

    def test_levels_within_swing_range(self):
        df = _zigzag()
        price = float(df["close"].iloc[-1])
        fib = calculate_fibonacci(df, price)
        lo, hi = fib.swing_low, fib.swing_high
        # ретрейсменты лежат между свингами (с допуском на расширения)
        span = hi - lo
        for lvl in fib.levels:
            assert lo - span <= lvl.price <= hi + span
