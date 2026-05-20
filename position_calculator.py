"""Расчёт стоп-лосса, тейк-профита и PnL по открытой позиции."""

from __future__ import annotations

from dataclasses import dataclass

from analyzer import MarketAnalysis, VolatilityMetrics


@dataclass
class PositionInput:
    entry_price: float
    margin_usdt: float
    leverage: int
    side: str  # "long" | "short"


@dataclass
class PositionResult:
    side: str
    side_label: str
    entry_price: float
    margin_usdt: float
    leverage: int
    position_notional_usdt: float
    quantity: float
    current_price: float
    stop_loss: float
    take_profit: float
    stop_reason: str
    tp_reason: str
    risk_reward: float
    sl_distance_pct: float
    tp_distance_pct: float
    pnl_current_usdt: float
    pnl_current_pct: float
    pnl_tp_usdt: float
    pnl_tp_pct: float
    pnl_sl_usdt: float
    pnl_sl_pct: float
    status: str
    advice: str


def _pick_stop_long(
    entry: float,
    supports: list[float],
    fib_levels: list[float],
    atr: float,
) -> tuple[float, str]:
    candidates = [s for s in supports if s < entry * 0.998]
    candidates += [f for f in fib_levels if f < entry * 0.998]
    atr_stop = entry - atr * 1.5
    candidates.append(atr_stop)
    candidates.append(entry * 0.985)

    stop = max(candidates) if candidates else atr_stop
    min_stop = entry * 0.97
    max_stop = entry * 0.995
    stop = max(min(stop, max_stop), min_stop)

    if stop in supports[:1] if supports else False:
        reason = "Стоп у ближайшей поддержки"
    elif any(abs(stop - f) < entry * 0.002 for f in fib_levels):
        reason = "Стоп у уровня Фибоначчи"
    else:
        reason = f"Стоп по ATR (1.5× ATR = ${atr:.2f})"
    return round(stop, 6), reason


def _pick_tp_long(entry: float, stop: float, resistances: list[float], fib_levels: list[float], atr: float) -> tuple[float, str]:
    risk = entry - stop
    min_rr_tp = entry + risk * 2

    candidates = [r for r in resistances if r > entry * 1.002]
    candidates += [f for f in fib_levels if f > entry * 1.002]
    candidates.append(entry + atr * 2.5)
    candidates.append(min_rr_tp)

    tp = min(candidates) if candidates else min_rr_tp
    tp = max(tp, min_rr_tp * 0.95)

    if tp in resistances[:1] if resistances else False:
        reason = "Тейк у сопротивления"
    elif any(abs(tp - f) < entry * 0.002 for f in fib_levels):
        reason = "Тейк у уровня Фибоначчи"
    else:
        reason = "Тейк по соотношению риск/прибыль 1:2"
    return round(tp, 6), reason


def _pick_stop_short(
    entry: float,
    resistances: list[float],
    fib_levels: list[float],
    atr: float,
) -> tuple[float, str]:
    candidates = [r for r in resistances if r > entry * 1.002]
    candidates += [f for f in fib_levels if f > entry * 1.002]
    atr_stop = entry + atr * 1.5
    candidates.append(atr_stop)
    candidates.append(entry * 1.015)

    stop = min(candidates) if candidates else atr_stop
    stop = min(max(stop, entry * 1.005), entry * 1.03)

    if stop in resistances[:1] if resistances else False:
        reason = "Стоп у сопротивления"
    elif any(abs(stop - f) < entry * 0.002 for f in fib_levels):
        reason = "Стоп у уровня Фибоначчи"
    else:
        reason = f"Стоп по ATR (1.5× ATR)"
    return round(stop, 6), reason


def _pick_tp_short(entry: float, stop: float, supports: list[float], fib_levels: list[float], atr: float) -> tuple[float, str]:
    risk = stop - entry
    min_rr_tp = entry - risk * 2

    candidates = [s for s in supports if s < entry * 0.998]
    candidates += [f for f in fib_levels if f < entry * 0.998]
    candidates.append(entry - atr * 2.5)
    candidates.append(min_rr_tp)

    tp = max(candidates) if candidates else min_rr_tp
    tp = min(tp, min_rr_tp * 1.05)

    if tp in supports[:1] if supports else False:
        reason = "Тейк у поддержки"
    elif any(abs(tp - f) < entry * 0.002 for f in fib_levels):
        reason = "Тейк у уровня Фибоначчи"
    else:
        reason = "Тейк по соотношению риск/прибыль 1:2"
    return round(tp, 6), reason


def _pnl(side: str, entry: float, exit_price: float, margin: float, leverage: int) -> tuple[float, float]:
    if side == "long":
        price_pct = (exit_price - entry) / entry
    else:
        price_pct = (entry - exit_price) / entry
    pnl_usdt = margin * leverage * price_pct
    pnl_pct = price_pct * leverage * 100
    return round(pnl_usdt, 2), round(pnl_pct, 2)


def calculate_position(analysis: MarketAnalysis, pos: PositionInput) -> PositionResult:
    entry = pos.entry_price
    margin = pos.margin_usdt
    lev = max(1, min(int(pos.leverage), 125))
    side = pos.side.lower().strip()
    if side in ("long", "лонг", "buy", "l"):
        side = "long"
    elif side in ("short", "шорт", "sell", "s"):
        side = "short"
    else:
        side = "long"

    current = analysis.price
    notional = margin * lev
    quantity = notional / entry if entry else 0

    atr = analysis.volatility.atr_14 if analysis.volatility else entry * 0.02
    fib_prices = [l.price for l in analysis.fibonacci.levels] if analysis.fibonacci else []

    if side == "long":
        stop, stop_reason = _pick_stop_long(entry, analysis.support_levels, fib_prices, atr)
        tp, tp_reason = _pick_tp_long(entry, stop, analysis.resistance_levels, fib_prices, atr)
        sl_dist = (entry - stop) / entry * 100
        tp_dist = (tp - entry) / entry * 100
    else:
        stop, stop_reason = _pick_stop_short(entry, analysis.resistance_levels, fib_prices, atr)
        tp, tp_reason = _pick_tp_short(entry, stop, analysis.support_levels, fib_prices, atr)
        sl_dist = (stop - entry) / entry * 100
        tp_dist = (entry - tp) / entry * 100

    risk = abs(entry - stop)
    reward = abs(tp - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0

    pnl_cur, pnl_cur_pct = _pnl(side, entry, current, margin, lev)
    pnl_tp, pnl_tp_pct = _pnl(side, entry, tp, margin, lev)
    pnl_sl, pnl_sl_pct = _pnl(side, entry, stop, margin, lev)

    if pnl_cur > 0:
        status = f"В плюсе +{pnl_cur:.2f} USDT (+{pnl_cur_pct:.2f}%)"
    elif pnl_cur < 0:
        status = f"В минусе {pnl_cur:.2f} USDT ({pnl_cur_pct:.2f}%)"
    else:
        status = "На точке входа (0 USDT)"

    advice_parts = []
    if side == "long" and analysis.trade:
        advice_parts.append(f"Рынок: лонг {analysis.trade.long_verdict}")
    elif analysis.trade:
        advice_parts.append(f"Рынок: шорт {analysis.trade.short_verdict}")

    if pnl_sl < -margin * 0.5:
        advice_parts.append("Стоп близко к ликвидации при сильном движении — уменьшите плечо")
    if rr >= 2:
        advice_parts.append(f"Соотношение R:R = 1:{rr} — хорошая цель")
    else:
        advice_parts.append(f"R:R = 1:{rr} — можно поднять тейк")

    advice = " · ".join(advice_parts) if advice_parts else "Следите за ценой и не перемещайте стоп против себя"

    return PositionResult(
        side=side,
        side_label="ЛОНГ 📈" if side == "long" else "ШОРТ 📉",
        entry_price=round(entry, 6),
        margin_usdt=round(margin, 2),
        leverage=lev,
        position_notional_usdt=round(notional, 2),
        quantity=round(quantity, 6),
        current_price=round(current, 6),
        stop_loss=stop,
        take_profit=tp,
        stop_reason=stop_reason,
        tp_reason=tp_reason,
        risk_reward=rr,
        sl_distance_pct=round(sl_dist, 2),
        tp_distance_pct=round(tp_dist, 2),
        pnl_current_usdt=pnl_cur,
        pnl_current_pct=pnl_cur_pct,
        pnl_tp_usdt=pnl_tp,
        pnl_tp_pct=pnl_tp_pct,
        pnl_sl_usdt=pnl_sl,
        pnl_sl_pct=pnl_sl_pct,
        status=status,
        advice=advice,
    )
