"""Менеджер рисков: размер позиции, лимиты, R:R, плечо."""

from __future__ import annotations

from dataclasses import dataclass, field

from tis.analysis.analyzer import MarketAnalysis
from tis.analysis.position_calculator import liquidation_price


@dataclass
class RiskInput:
    balance_usdt: float
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_portfolio_risk_pct: float = 6.0
    entry: float = 0
    stop: float = 0
    take_profit: float | None = None
    side: str = "long"
    leverage: int | None = None
    margin_usdt: float | None = None
    daily_loss_used_pct: float = 0.0
    open_trades: int = 0


@dataclass
class RiskPlan:
    verdict: str
    status: str
    risk_budget_usdt: float
    risk_per_trade_pct: float
    actual_risk_usdt: float
    actual_risk_pct: float
    recommended_margin_usdt: float
    recommended_notional_usdt: float
    recommended_leverage: int
    max_safe_leverage: int
    position_quantity: float
    stop_distance_pct: float
    take_profit_distance_pct: float | None
    liquidation_price: float | None
    liquidation_distance_pct: float | None
    stop_before_liquidation: bool
    risk_reward: float
    max_loss_at_stop_usdt: float
    potential_profit_usdt: float | None
    daily_budget_left_usdt: float
    daily_budget_left_pct: float
    portfolio_headroom_pct: float
    kelly_fraction_pct: float | None
    warnings: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)
    rules_checklist: list[str] = field(default_factory=list)


def _normalize_side(side: str) -> str:
    s = side.lower().strip()
    if s in ("short", "шорт", "sell", "s"):
        return "short"
    return "long"


def _validate_stop(entry: float, stop: float, side: str) -> float:
    if entry <= 0 or stop <= 0:
        raise ValueError("Цена входа и стоп должны быть больше 0")
    if side == "long" and stop >= entry:
        raise ValueError("Для лонга стоп должен быть ниже входа")
    if side == "short" and stop <= entry:
        raise ValueError("Для шорта стоп должен быть выше входа")
    return abs(entry - stop) / entry


def _max_leverage_for_stop(stop_dist_pct: float, max_margin_loss_pct: float = 80.0) -> int:
    if stop_dist_pct <= 0:
        return 1
    lev = int(max_margin_loss_pct / (stop_dist_pct * 100))
    return max(1, min(lev, 125))


def calculate_risk_plan(inp: RiskInput, analysis: MarketAnalysis | None = None) -> RiskPlan:
    balance = float(inp.balance_usdt)
    if balance <= 0:
        raise ValueError("Депозит должен быть больше 0")

    risk_pct = max(0.1, min(float(inp.risk_per_trade_pct), 10.0))
    max_daily_pct = max(0.5, min(float(inp.max_daily_loss_pct), 20.0))
    max_portfolio_pct = max(risk_pct, min(float(inp.max_portfolio_risk_pct), 25.0))

    entry = float(inp.entry)
    stop = float(inp.stop)
    side = _normalize_side(inp.side)
    stop_dist = _validate_stop(entry, stop, side)

    lev = max(1, min(int(inp.leverage or 10), 125))
    tp = float(inp.take_profit) if inp.take_profit else None

    risk_budget = round(balance * risk_pct / 100, 2)
    daily_budget = round(balance * max_daily_pct / 100, 2)
    daily_used = round(balance * max(0, inp.daily_loss_used_pct) / 100, 2)
    daily_left = round(max(0, daily_budget - daily_used), 2)
    daily_left_pct = round(daily_left / balance * 100, 2) if balance else 0

    portfolio_cap = balance * max_portfolio_pct / 100
    portfolio_headroom = round(
        max(0, (portfolio_cap - risk_budget * max(1, inp.open_trades)) / balance * 100), 2
    )

    recommended_notional = risk_budget / stop_dist if stop_dist > 0 else 0
    recommended_margin = round(recommended_notional / lev, 2)
    recommended_notional = round(recommended_notional, 2)
    max_safe_lev = _max_leverage_for_stop(stop_dist)
    recommended_lev = min(lev, max_safe_lev)

    liq = liquidation_price(entry, lev, side)
    liq_dist_pct = None
    stop_before_liq = True
    if liq is not None:
        liq_dist_pct = round(abs(entry - liq) / entry * 100, 2)
        stop_before_liq = stop > liq if side == "long" else stop < liq

    margin = float(inp.margin_usdt) if inp.margin_usdt and inp.margin_usdt > 0 else recommended_margin
    notional = margin * lev
    quantity = notional / entry if entry else 0
    actual_risk = round(notional * stop_dist, 2)
    actual_risk_pct = round(actual_risk / balance * 100, 2) if balance else 0

    max_loss = actual_risk
    potential_profit = None
    tp_dist_pct = None
    rr = 0.0
    if tp:
        if side == "long":
            tp_dist_pct = (tp - entry) / entry * 100
            reward = tp - entry
        else:
            tp_dist_pct = (entry - tp) / entry * 100
            reward = entry - tp
        risk_price = abs(entry - stop)
        rr = round(reward / risk_price, 2) if risk_price > 0 else 0
        potential_profit = round(notional * (reward / entry), 2)

    warnings: list[str] = []
    tips: list[str] = []
    rules: list[str] = []

    if actual_risk > risk_budget * 1.05:
        warnings.append(
            f"Риск ${actual_risk:.2f} превышает лимит ${risk_budget:.2f} ({risk_pct}% депозита)"
        )
    if actual_risk > daily_left:
        warnings.append(f"Риск сделки больше остатка дневного лимита (${daily_left:.2f})")
    if lev > max_safe_lev:
        warnings.append(
            f"Плечо x{lev} опасно при стопе {stop_dist*100:.2f}% — рекомендуем ≤ x{max_safe_lev}"
        )
    if margin * lev * stop_dist > balance * 0.5:
        warnings.append("Потеря по стопу >50% депозита — критический размер")
    if liq is not None and not stop_before_liq:
        warnings.append(
            f"Ликвидация (${liq:,.4f}, {liq_dist_pct}%) наступит раньше стопа — снизьте плечо"
        )
    if rr and rr < 2:
        warnings.append(f"R:R 1:{rr} — ниже рекомендуемого 1:2.5")
    if analysis and analysis.trade:
        bias = analysis.bias.direction if analysis.bias else "neutral"
        if (side == "long" and bias == "short") or (side == "short" and bias == "long"):
            warnings.append("Сделка против HTF bias — снизьте риск до 0.5%")

    if not warnings:
        tips.append(f"Размер в норме: риск ~{actual_risk_pct:.2f}% от депозита")
    tips.append(f"Оптимальная маржа при x{recommended_lev}: ${recommended_margin:.2f}")
    tips.append("Фиксируйте 30–50% на TP1, остаток — по трейлингу")
    if analysis and analysis.volatility:
        tips.append(f"ATR {analysis.volatility.atr_percent:.2f}% — учитывайте в ширине стопа")

    rules.append(f"Риск на сделку: ≤ {risk_pct}% (${risk_budget:.2f})")
    rules.append(f"Дневной лимит: ≤ {max_daily_pct}% (осталось ${daily_left:.2f})")
    rules.append(f"Суммарный риск портфеля: ≤ {max_portfolio_pct}%")
    rules.append(f"Стоп обязателен: {stop_dist*100:.2f}% от входа")

    kelly = None
    if analysis and analysis.trade and rr >= 1:
        win_rate = (
            analysis.trade.long_score / 100
            if side == "long"
            else analysis.trade.short_score / 100
        )
        win_rate = max(0.35, min(0.65, win_rate))
        kelly_raw = win_rate - (1 - win_rate) / rr
        kelly = round(max(0, kelly_raw) * 100, 2)

    if not warnings and actual_risk <= risk_budget:
        verdict = "Риск в пределах правил"
        status = "ok"
    elif warnings and actual_risk <= risk_budget * 1.2:
        verdict = "Допустимо с осторожностью"
        status = "warn"
    else:
        verdict = "Риск превышен — уменьшите позицию"
        status = "danger"

    return RiskPlan(
        verdict=verdict,
        status=status,
        risk_budget_usdt=risk_budget,
        risk_per_trade_pct=risk_pct,
        actual_risk_usdt=actual_risk,
        actual_risk_pct=actual_risk_pct,
        recommended_margin_usdt=recommended_margin,
        recommended_notional_usdt=recommended_notional,
        recommended_leverage=recommended_lev,
        max_safe_leverage=max_safe_lev,
        position_quantity=round(quantity, 6),
        stop_distance_pct=round(stop_dist * 100, 2),
        take_profit_distance_pct=round(tp_dist_pct, 2) if tp_dist_pct else None,
        liquidation_price=liq,
        liquidation_distance_pct=liq_dist_pct,
        stop_before_liquidation=stop_before_liq,
        risk_reward=rr,
        max_loss_at_stop_usdt=max_loss,
        potential_profit_usdt=potential_profit,
        daily_budget_left_usdt=daily_left,
        daily_budget_left_pct=daily_left_pct,
        portfolio_headroom_pct=portfolio_headroom,
        kelly_fraction_pct=kelly,
        warnings=warnings,
        tips=tips,
        rules_checklist=rules,
    )
