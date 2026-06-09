"""Тесты индикаторов и агрегатов analyzer (детерминированно, на синтетике)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tis.analysis.analyzer import (
    TimeframeAnalysis,
    _atr,
    _calculate_macd,
    _ema,
    _rsi,
    determine_overall_trend,
    find_support_resistance,
)


def _ohlc(closes: list[float], spread: float = 1.0) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "open_time": pd.date_range("2024-01-01", periods=n, freq="h"),
        "open": closes,
        "high": [c + spread for c in closes],
        "low": [c - spread for c in closes],
        "close": closes,
        "volume": [1000.0] * n,
    })


class TestEma:
    def test_known_value(self):
        # span=3 → alpha=0.5; рекурсия по [1..5] даёт последнюю EMA 4.0625
        ema = _ema(pd.Series([1, 2, 3, 4, 5]), 3)
        assert abs(float(ema.iloc[-1]) - 4.0625) < 1e-9

    def test_constant_series_equals_value(self):
        ema = _ema(pd.Series([7.0] * 20), 10)
        assert abs(float(ema.iloc[-1]) - 7.0) < 1e-9


class TestRsi:
    def test_flat_series_is_neutral(self):
        assert _rsi(pd.Series([100.0] * 30)) == 50.0

    def test_strong_uptrend_high(self):
        # рост с мелкими откатами (чтобы loss>0 и RSI не схлопнулся в 50)
        s = []
        v = 100.0
        for i in range(60):
            v += 2.0 if i % 5 else -0.5
            s.append(v)
        assert _rsi(pd.Series(s)) > 60

    def test_strong_downtrend_low(self):
        s = []
        v = 100.0
        for i in range(60):
            v -= 2.0 if i % 5 else -0.5
            s.append(v)
        assert _rsi(pd.Series(s)) < 40


class TestAtr:
    def test_positive(self):
        df = _ohlc([100 + (i % 3) for i in range(40)])
        assert _atr(df) > 0

    def test_constant_range_converges(self):
        # high-low = 2 на каждой свече, close постоянный → ATR → 2
        df = _ohlc([100.0] * 60, spread=1.0)
        assert abs(_atr(df) - 2.0) < 1e-6


class TestMacd:
    def test_keys_present(self):
        df = _ohlc([100 + i * 0.5 for i in range(60)])
        m = _calculate_macd(df["close"])
        assert {"macd", "signal", "histogram", "trend", "cross", "momentum"} <= set(m)

    def test_uptrend_macd_above_signal(self):
        m = _calculate_macd(pd.Series([100 + i for i in range(80)]))
        assert m["macd"] > m["signal"]
        assert "ыч" in m["trend"].lower() or "БЫЧ" in m["trend"]  # бычий


def _tf(timeframe: str, trend: str) -> TimeframeAnalysis:
    return TimeframeAnalysis(
        timeframe=timeframe, trend=trend, trend_strength="",
        rsi=50, ema20=100, ema50=100, sma200=None, price=100, change_pct=0,
        macd=0, macd_signal=0, macd_histogram=0, macd_trend="", macd_cross="",
    )


class TestOverallTrend:
    def test_all_bullish(self):
        tfs = [_tf("1d", "БЫЧИЙ 📈"), _tf("4h", "БЫЧИЙ 📈"), _tf("1h", "БЫЧИЙ 📈")]
        label, _ = determine_overall_trend(tfs)
        assert "БЫЧИЙ" in label

    def test_all_bearish(self):
        tfs = [_tf("1d", "МЕДВЕЖИЙ 📉"), _tf("4h", "МЕДВЕЖИЙ 📉"), _tf("1h", "МЕДВЕЖИЙ 📉")]
        label, _ = determine_overall_trend(tfs)
        assert "МЕДВЕЖИЙ" in label

    def test_mixed_is_neutral(self):
        tfs = [_tf("1d", "БЫЧИЙ 📈"), _tf("4h", "МЕДВЕЖИЙ 📉")]
        label, _ = determine_overall_trend(tfs)
        assert "СМЕШАННЫЙ" in label

    def test_empty_no_data(self):
        label, note = determine_overall_trend([])
        assert "СМЕШАННЫЙ" in label


def _zigzag(n: int = 50) -> pd.DataFrame:
    vals = []
    for i in range(n):
        p = i % 10
        vals.append(90 + 4 * p if p <= 5 else 110 - 4 * (p - 5))
    return _ohlc([float(v) for v in vals], spread=0.5)


class TestSupportResistance:
    def test_supports_below_resistances_above(self):
        df = _zigzag()
        price = float(df["close"].iloc[-1])
        supports, resistances = find_support_resistance(df, price)
        assert supports and all(s < price for s in supports)
        assert resistances and all(r > price for r in resistances)
