"""Тесты Smart Money Concepts (SMC) — детерминированно, на синтетике, без сети."""

from __future__ import annotations

import pandas as pd

from tis.analysis.smc import (
    _bos_choch,
    _order_blocks,
    _premium_discount,
    analyze_smc,
)


def _df(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """rows = [(open, high, low, close), ...]"""
    n = len(rows)
    return pd.DataFrame({
        "open_time": pd.date_range("2024-01-01", periods=n, freq="h"),
        "open": [r[0] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[2] for r in rows],
        "close": [r[3] for r in rows],
        "volume": [1000.0] * n,
    })


def _trend_df(direction: str, cycles: int = 6) -> pd.DataFrame:
    """Зигзаг с явными свингами; общий дрейф вверх/вниз по циклам."""
    hump = [0, 3, 6, 9, 6, 3, 0, -3]  # свинг-хай на фазе 3, свинг-лоу на фазе 7
    start = 100.0 if direction == "up" else 200.0
    cyclestep = 10.0 if direction == "up" else -10.0
    rows = []
    for c in range(cycles):
        base = start + c * cyclestep
        for ph in range(8):
            v = base + hump[ph]
            rows.append((v, v + 0.5, v - 0.5, v))
    return _df(rows)


class TestPremiumDiscount:
    def test_discount_zone_near_low(self):
        df = _df([(100, 200, 100, 150)] * 5)  # диапазон 100..200
        z = _premium_discount(df, price=110)
        assert z["zone"] == "discount"
        assert z["pct"] < 0.34

    def test_premium_zone_near_high(self):
        df = _df([(100, 200, 100, 150)] * 5)
        z = _premium_discount(df, price=190)
        assert z["zone"] == "premium"
        assert z["pct"] > 0.66

    def test_equilibrium_middle(self):
        df = _df([(100, 200, 100, 150)] * 5)
        z = _premium_discount(df, price=150)
        assert z["zone"] == "equilibrium"


class TestBosChoch:
    def test_breakout_up_is_long_event(self):
        df = _trend_df("down")
        # добиваем баром, который закрывается ВЫШЕ последнего свинг-хая
        top = float(df["high"].max()) + 5
        df2 = pd.concat([df, _df([(top - 1, top + 1, top - 2, top)])], ignore_index=True)
        ev = _bos_choch(df2)
        assert ev["direction"] == "long"
        assert ev["event"] in ("BOS", "CHoCH")

    def test_breakdown_is_short_event(self):
        df = _trend_df("up")
        bot = float(df["low"].min()) - 5
        df2 = pd.concat([df, _df([(bot + 1, bot + 2, bot - 1, bot)])], ignore_index=True)
        ev = _bos_choch(df2)
        assert ev["direction"] == "short"

    def test_inside_structure_neutral(self):
        df = _df([(100, 101, 99, 100)] * 30)  # плоско, без свингов
        ev = _bos_choch(df)
        assert ev["direction"] == "neutral"


class TestOrderBlocks:
    def test_bullish_order_block_before_impulse(self):
        rows = [(100, 100.6, 99.4, 100.2), (100.2, 100.8, 99.6, 100.0)] * 3  # мелкие тела
        rows.append((103.0, 103.2, 102.0, 102.2))  # медвежья свеча (последняя перед импульсом)
        rows.append((102.2, 112.0, 102.0, 111.0))  # сильный бычий импульс
        rows += [(111, 111.5, 110.5, 111)] * 3      # без отработки OB вниз
        df = _df(rows)
        obs = _order_blocks(df, price=111)
        assert any(o["kind"] == "bullish" for o in obs)


class TestAnalyzeSmc:
    def test_contract_keys(self):
        df = _trend_df("up")
        smc = analyze_smc(df, price=float(df["close"].iloc[-1]))
        assert smc is not None
        for k in ("smc_bias", "premium_discount", "liquidity_sweeps", "order_blocks", "bos_choch", "summary"):
            assert k in smc
        assert smc["smc_bias"] in ("long", "short", "neutral")

    def test_none_on_short_data(self):
        assert analyze_smc(_df([(1, 2, 0.5, 1.5)] * 5), price=1.5) is None
        assert analyze_smc(None, price=100) is None
