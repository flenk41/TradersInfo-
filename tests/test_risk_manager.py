"""Юнит-тесты менеджера рисков."""

from __future__ import annotations

import pytest

from risk_manager import RiskInput, calculate_risk_plan


class TestValidation:
    def test_zero_balance_raises(self):
        with pytest.raises(ValueError):
            calculate_risk_plan(RiskInput(balance_usdt=0, entry=100, stop=95, side="long"))

    def test_long_stop_above_entry_raises(self):
        with pytest.raises(ValueError):
            calculate_risk_plan(RiskInput(balance_usdt=1000, entry=100, stop=105, side="long"))

    def test_short_stop_below_entry_raises(self):
        with pytest.raises(ValueError):
            calculate_risk_plan(RiskInput(balance_usdt=1000, entry=100, stop=95, side="short"))

    def test_nonpositive_entry_raises(self):
        with pytest.raises(ValueError):
            calculate_risk_plan(RiskInput(balance_usdt=1000, entry=0, stop=95, side="long"))


class TestPlanMath:
    def _plan(self, **kw):
        base = dict(balance_usdt=1000, risk_per_trade_pct=1, entry=100, stop=95,
                    side="long", leverage=10)
        base.update(kw)
        return calculate_risk_plan(RiskInput(**base))

    def test_stop_distance_pct(self):
        assert self._plan().stop_distance_pct == 5.0

    def test_risk_budget(self):
        assert self._plan().risk_budget_usdt == 10.0

    def test_recommended_sizing(self):
        plan = self._plan()
        # бюджет 10 при стопе 5% → ноционал 200, маржа при x10 → 20
        assert plan.recommended_notional_usdt == 200.0
        assert plan.recommended_margin_usdt == 20.0

    def test_rr_with_take_profit(self):
        plan = self._plan(take_profit=110)
        assert plan.risk_reward == 2.0

    def test_max_safe_leverage_in_bounds(self):
        plan = self._plan(stop=99, leverage=125)
        assert 1 <= plan.max_safe_leverage <= 125

    def test_liquidation_below_entry_for_long(self):
        plan = self._plan(leverage=20)
        assert plan.liquidation_price is not None
        assert plan.liquidation_price < 100

    def test_status_is_valid_label(self):
        assert self._plan().status in ("ok", "warn", "danger")

    def test_short_side_liquidation_above_entry(self):
        plan = calculate_risk_plan(
            RiskInput(balance_usdt=1000, entry=100, stop=105, side="short", leverage=20)
        )
        assert plan.liquidation_price is not None
        assert plan.liquidation_price > 100
