"""Стоп/тейк за структурой + минимум R:R 1:2.5."""

from __future__ import annotations

from dataclasses import dataclass

from analyzer import MarketAnalysis


@dataclass
class PositionInput:
    entry_price: float
    margin_usdt: float
    leverage: int
    side: str


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
    take_profit_2: float | None
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
    aligned_with_market: bool


MIN_RR = 2.5
ATR_STOP_MULT = 1.5
ATR_BUFFER = 0.25


def _pnl(side: str, entry: float, exit_price: float, margin: float, leverage: int) -> tuple[float, float]:
    price_pct = (exit_price - entry) / entry if side == "long" else (entry - exit_price) / entry
    return round(margin * leverage * price_pct, 2), round(price_pct * leverage * 100, 2)


def _stop_long(entry: float, supports: list[float], fib: list[float], atr: float) -> tuple[float, str]:
    buffer = atr * ATR_BUFFER
    structural = [s for s in supports if s < entry * 0.998]
    structural += [f for f in fib if f < entry * 0.998]
    if structural:
        stop = max(structural) - buffer
        return round(max(stop, entry - atr * 3), 6), "Стоп за структурой (пивот/поддержка) + буфер ATR"
    stop = entry - atr * ATR_STOP_MULT
    return round(stop, 6), f"Стоп {ATR_STOP_MULT}×ATR — нет близкой поддержки"


def _tp_long(entry: float, stop: float, resistances: list[float], fib: list[float], atr: float) -> tuple[float, float | None, str]:
    risk = entry - stop
    min_tp = entry + risk * MIN_RR
    targets = sorted([r for r in resistances if r >= min_tp * 0.98] + [f for f in fib if f >= min_tp * 0.98])
    tp1 = targets[0] if targets else entry + atr * 2
    tp1 = max(tp1, min_tp)
    tp2 = targets[1] if len(targets) > 1 else round(entry + risk * 3.5, 6)
    reason = "TP1 у сопротивления, TP2 — расширение" if targets else f"TP по R:R 1:{MIN_RR}"
    return round(tp1, 6), round(tp2, 6) if tp2 > tp1 else None, reason


def _stop_short(entry: float, resistances: list[float], fib: list[float], atr: float) -> tuple[float, str]:
    buffer = atr * ATR_BUFFER
    structural = [r for r in resistances if r > entry * 1.002]
    structural += [f for f in fib if f > entry * 1.002]
    if structural:
        stop = min(structural) + buffer
        return round(min(stop, entry + atr * 3), 6), "Стоп за структурой (пивот/сопр.) + буфер ATR"
    stop = entry + atr * ATR_STOP_MULT
    return round(stop, 6), f"Стоп {ATR_STOP_MULT}×ATR над входом"


def _tp_short(entry: float, stop: float, supports: list[float], fib: list[float], atr: float) -> tuple[float, float | None, str]:
    risk = stop - entry
    min_tp = entry - risk * MIN_RR
    targets = sorted([s for s in supports if s <= min_tp * 1.02] + [f for f in fib if f <= min_tp * 1.02], reverse=True)
    tp1 = targets[0] if targets else entry - atr * 2
    tp1 = min(tp1, min_tp)
    tp2 = targets[1] if len(targets) > 1 else round(entry - risk * 3.5, 6)
    reason = "TP1 у поддержки, TP2 — расширение" if targets else f"TP по R:R 1:{MIN_RR}"
    return round(tp1, 6), round(tp2, 6) if tp2 < tp1 else None, reason


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
        stop, stop_reason = _stop_long(entry, analysis.support_levels, fib_prices, atr)
        tp, tp2, tp_reason = _tp_long(entry, stop, analysis.resistance_levels, fib_prices, atr)
        sl_dist = (entry - stop) / entry * 100
        tp_dist = (tp - entry) / entry * 100
    else:
        stop, stop_reason = _stop_short(entry, analysis.resistance_levels, fib_prices, atr)
        tp, tp2, tp_reason = _tp_short(entry, stop, analysis.support_levels, fib_prices, atr)
        sl_dist = (stop - entry) / entry * 100
        tp_dist = (entry - tp) / entry * 100

    risk = abs(entry - stop)
    reward = abs(tp - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0

    pnl_cur, pnl_cur_pct = _pnl(side, entry, current, margin, lev)
    pnl_tp, pnl_tp_pct = _pnl(side, entry, tp, margin, lev)
    pnl_sl, pnl_sl_pct = _pnl(side, entry, stop, margin, lev)

    aligned = False
    if analysis.bias:
        aligned = (side == "long" and analysis.bias.direction == "long") or (
            side == "short" and analysis.bias.direction == "short"
        )

    if pnl_cur > 0:
        status = f"В плюсе +{pnl_cur:.2f} USDT (+{pnl_cur_pct:.2f}%)"
    elif pnl_cur < 0:
        status = f"В минусе {pnl_cur:.2f} USDT ({pnl_cur_pct:.2f}%)"
    else:
        status = "На точке входа"

    advice_parts = []
    if not aligned:
        advice_parts.append("⚠ Позиция против HTF bias — уменьшите размер или закройте")
    elif analysis.trade:
        v = analysis.trade.long_verdict if side == "long" else analysis.trade.short_verdict
        advice_parts.append(f"Рынок: {v}")
    if abs(pnl_sl) > margin * 0.8:
        advice_parts.append("Стоп >80% маржи — плечо слишком высокое")
    if rr >= MIN_RR:
        advice_parts.append(f"R:R 1:{rr} — фиксируйте 50% на TP1")
    if tp2:
        advice_parts.append(f"TP2: ${tp2:,.4f} (остаток позиции)")

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
        take_profit_2=tp2,
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
        advice=" · ".join(advice_parts) if advice_parts else "Держите стоп, не переносите в минус",
        aligned_with_market=aligned,
    )
