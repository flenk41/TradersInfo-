"""Юнит-тесты расчёта позиции и цены ликвидации."""

from __future__ import annotations

from tis.analysis.analyzer import MarketAnalysis
from tis.analysis.position_calculator import (
    MIN_RR,
    PositionInput,
    calculate_position,
    liquidation_price,
    zone_stop_take,
)


def _analysis(price: float = 100.0, supports=None, resistances=None) -> MarketAnalysis:
    return MarketAnalysis(
        symbol="TEST",
        price=price,
        change_24h_pct=0.0,
        high_24h=price * 1.1,
        low_24h=price * 0.9,
        volume_24h=1000.0,
        overall_trend="БОКОВОЙ",
        trend_summary="тест",
        support_levels=supports or [],
        resistance_levels=resistances or [],
    )


class TestLiquidationPrice:
    def test_no_liquidation_at_low_leverage(self):
        assert liquidation_price(100, 1, "long") is None
        assert liquidation_price(100, 0, "long") is None

    def test_invalid_entry_returns_none(self):
        assert liquidation_price(0, 10, "long") is None
        assert liquidation_price(-5, 10, "long") is None

    def test_long_liquidation_below_entry(self):
        liq = liquidation_price(100, 10, "long")
        assert liq is not None and liq < 100

    def test_short_liquidation_above_entry(self):
        liq = liquidation_price(100, 10, "short")
        assert liq is not None and liq > 100

    def test_higher_leverage_closer_to_entry_long(self):
        assert liquidation_price(100, 50, "long") > liquidation_price(100, 5, "long")

    def test_higher_leverage_closer_to_entry_short(self):
        assert liquidation_price(100, 50, "short") < liquidation_price(100, 5, "short")

    def test_fees_make_long_more_conservative(self):
        with_fee = liquidation_price(100, 10, "long", mmr=0.0, fee_rate=0.001)
        no_fee = liquidation_price(100, 10, "long", mmr=0.0, fee_rate=0.0)
        assert with_fee > no_fee

    def test_known_value_long_no_fee_no_mmr(self):
        liq = liquidation_price(100, 10, "long", mmr=0.0, fee_rate=0.0)
        assert abs(liq - 90.0) < 1e-6

    def test_known_value_short_no_fee_no_mmr(self):
        liq = liquidation_price(100, 10, "short", mmr=0.0, fee_rate=0.0)
        assert abs(liq - 110.0) < 1e-6


class TestCalculatePosition:
    def test_long_levels_ordered(self):
        pos = calculate_position(_analysis(100), PositionInput(100, 100, 10, "long"))
        assert pos.stop_loss < pos.entry_price < pos.take_profit

    def test_short_levels_ordered(self):
        pos = calculate_position(_analysis(100), PositionInput(100, 100, 10, "short"))
        assert pos.take_profit < pos.entry_price < pos.stop_loss

    def test_min_rr_enforced(self):
        pos = calculate_position(_analysis(100), PositionInput(100, 100, 10, "long"))
        assert pos.risk_reward >= MIN_RR - 0.01

    def test_leverage_clamped_to_125(self):
        pos = calculate_position(_analysis(100), PositionInput(100, 100, 999, "long"))
        assert pos.leverage <= 125

    def test_notional_and_quantity(self):
        pos = calculate_position(_analysis(100), PositionInput(100, 100, 10, "long"))
        assert abs(pos.position_notional_usdt - 1000.0) < 1e-6
        assert abs(pos.quantity - 10.0) < 1e-6

    def test_long_liquidation_present(self):
        pos = calculate_position(_analysis(100), PositionInput(100, 100, 10, "long"))
        assert pos.liquidation_price is not None and pos.liquidation_price < 100

    def test_side_normalization(self):
        long_ru = calculate_position(_analysis(100), PositionInput(100, 100, 10, "ЛОНГ"))
        short_en = calculate_position(_analysis(100), PositionInput(100, 100, 10, "sell"))
        assert long_ru.side == "long"
        assert short_en.side == "short"

    def test_stop_uses_structure_when_available(self):
        # ближайшая поддержка 97 → стоп должен быть рядом с ней (ниже входа)
        pos = calculate_position(
            _analysis(100, supports=[97.0], resistances=[106.0]),
            PositionInput(100, 100, 10, "long"),
        )
        assert pos.stop_loss < 100
        assert pos.stop_loss <= 97.0


class TestZoneStopTake:
    """Единая методология стоп/тейк (используется графиком и расчётом позиции)."""

    def test_long_order_and_min_rr(self):
        stop, tp = zone_stop_take("long", 100.0, supports=[96.0], resistances=[110.0],
                                  fib_prices=[], atr=2.0)
        assert stop < 100.0 < tp
        rr = (tp - 100.0) / (100.0 - stop)
        assert rr >= MIN_RR - 1e-6

    def test_short_order_and_min_rr(self):
        stop, tp = zone_stop_take("short", 100.0, supports=[90.0], resistances=[104.0],
                                  fib_prices=[], atr=2.0)
        assert tp < 100.0 < stop
        rr = (100.0 - tp) / (stop - 100.0)
        assert rr >= MIN_RR - 1e-6

    def test_min_stop_distance_when_level_too_close(self):
        # поддержка вплотную к входу (99.99) → стоп отодвигается на min_stop×ATR,
        # чтобы шум не выбивал позицию (а не лепится к 99.99)
        stop, _tp = zone_stop_take("long", 100.0, supports=[99.99], resistances=[110.0],
                                   fib_prices=[], atr=2.0)
        assert stop < 99.0  # отодвинут заметно ниже близкого уровня

    def test_matches_calculate_position_direction(self):
        # zone_stop_take и calculate_position дают согласованные знаки уровней
        stop, tp = zone_stop_take("long", 100.0, supports=[96.0], resistances=[110.0],
                                  fib_prices=[], atr=2.0)
        pos = calculate_position(
            _analysis(100, supports=[96.0], resistances=[110.0]),
            PositionInput(100, 100, 10, "long"),
        )
        assert (stop < 100 < tp) and (pos.stop_loss < 100 < pos.take_profit)
