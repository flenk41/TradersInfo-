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
    liquidation_price: float | None
    liquidation_distance_pct: float | None
    stop_before_liquidation: bool
    stop_reason: str
    tp_reason: str
    methodology: str
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


# Минимум R:R 1:2 — при таком соотношении достаточно ~40% прибыльных сделок.
MIN_RR = 2.0
TP2_RR = 3.5

# Ставка поддерживающей маржи (maintenance margin rate) для оценки ликвидации.
# Усреднённое значение для изолированной маржи; реальная зависит от биржи и тира позиции.
DEFAULT_MMR = 0.005

# Тейкерская комиссия за сторону (≈0.05% на фьючерсах Binance). Учитываем вход+выход,
# чтобы оценка ликвидации была консервативной, а не оптимистичной.
DEFAULT_TAKER_FEE = 0.0005


def liquidation_price(
    entry: float,
    leverage: int,
    side: str,
    mmr: float = DEFAULT_MMR,
    fee_rate: float = DEFAULT_TAKER_FEE,
) -> float | None:
    """Оценка цены ликвидации для изолированной маржи с учётом комиссий.

    Выводится из условия «маржа − убыток − комиссии = поддерживающая маржа»:

        long:  P = entry · (1 − 1/L + fee) / (1 − mmr − fee)
        short: P = entry · (1 + 1/L − fee) / (1 + mmr + fee)

    Учёт fee и mmr делает оценку чуть консервативнее (ликвидация ближе к входу),
    чем «голая» формула entry·(1 ∓ 1/L). Это приближение: реальная цена зависит
    от тиров маржи биржи и режима маржи. При плече ≤ x1 ликвидации практически
    нет — возвращаем None.
    """
    if entry <= 0 or leverage <= 1:
        return None
    inv = 1.0 / leverage
    if side == "long":
        denom = 1.0 - mmr - fee_rate
        price = entry * (1.0 - inv + fee_rate) / denom if denom > 0 else 0.0
    else:
        price = entry * (1.0 + inv - fee_rate) / (1.0 + mmr + fee_rate)
    return round(max(price, 0.0), 6)

# Множитель ATR для стопа и буфер за структурой адаптируются к волатильности.
# Высокая волатильность → шире стоп (меньше выбьет шумом), низкая → плотнее.
_REGIME = {
    "high": {"stop_mult": 2.8, "buffer": 0.5, "min_stop": 1.2, "label": "высокая волатильность"},
    "medium": {"stop_mult": 2.0, "buffer": 0.3, "min_stop": 0.9, "label": "средняя волатильность"},
    "low": {"stop_mult": 1.5, "buffer": 0.2, "min_stop": 0.7, "label": "низкая волатильность"},
}


def _regime(volatility) -> dict:
    level = (getattr(volatility, "level", "") or "").upper()
    if "ВЫСОК" in level:
        return _REGIME["high"]
    if "НИЗК" in level:
        return _REGIME["low"]
    return _REGIME["medium"]


def _pnl(side: str, entry: float, exit_price: float, margin: float, leverage: int) -> tuple[float, float]:
    price_pct = (exit_price - entry) / entry if side == "long" else (entry - exit_price) / entry
    return round(margin * leverage * price_pct, 2), round(price_pct * leverage * 100, 2)


def _stop_long(entry: float, supports: list[float], fib: list[float], atr: float, reg: dict) -> tuple[float, str]:
    buffer = atr * reg["buffer"]
    cap = entry - atr * (reg["stop_mult"] + 1.5)
    min_dist = atr * reg["min_stop"]  # минимум, чтобы стоп не стоял в шуме
    structural = [s for s in supports if s < entry * 0.998]
    structural += [f for f in fib if f < entry * 0.998]
    if structural:
        stop = max(structural) - buffer
        # Не ближе минимальной дистанции (иначе выбьет шумом) и не дальше cap.
        stop = min(stop, entry - min_dist)
        too_close = (max(structural) - buffer) > entry - min_dist
        reason = (
            "Стоп за поддержкой/пивотом + буфер ATR"
            if not too_close
            else f"Поддержка близко — стоп отодвинут на {reg['min_stop']:g}×ATR (защита от шума)"
        )
        return round(max(stop, cap), 6), reason
    stop = entry - atr * reg["stop_mult"]
    return round(stop, 6), f"Стоп {reg['stop_mult']:g}×ATR ({reg['label']}) — нет близкой поддержки"


def _tp_long(entry: float, stop: float, resistances: list[float], fib: list[float], atr: float) -> tuple[float, float | None, str]:
    risk = entry - stop
    min_tp = entry + risk * MIN_RR
    targets = sorted([r for r in resistances if r >= min_tp * 0.98] + [f for f in fib if f >= min_tp * 0.98])
    tp1 = targets[0] if targets else entry + risk * MIN_RR
    tp1 = max(tp1, min_tp)
    further = [t for t in targets if t > tp1 * 1.001]
    tp2 = further[0] if further else round(entry + risk * TP2_RR, 6)
    reason = "TP1 у ближайшего сопротивления (R:R ≥ 1:2), TP2 — расширение" if targets else f"TP по R:R 1:{MIN_RR:g} (нет уровня выше)"
    return round(tp1, 6), round(tp2, 6), reason


def _stop_short(entry: float, resistances: list[float], fib: list[float], atr: float, reg: dict) -> tuple[float, str]:
    buffer = atr * reg["buffer"]
    cap = entry + atr * (reg["stop_mult"] + 1.5)
    min_dist = atr * reg["min_stop"]  # минимум, чтобы стоп не стоял в шуме
    structural = [r for r in resistances if r > entry * 1.002]
    structural += [f for f in fib if f > entry * 1.002]
    if structural:
        stop = min(structural) + buffer
        # Не ближе минимальной дистанции (иначе выбьет шумом) и не дальше cap.
        stop = max(stop, entry + min_dist)
        too_close = (min(structural) + buffer) < entry + min_dist
        reason = (
            "Стоп за сопротивлением/пивотом + буфер ATR"
            if not too_close
            else f"Сопротивление близко — стоп отодвинут на {reg['min_stop']:g}×ATR (защита от шума)"
        )
        return round(min(stop, cap), 6), reason
    stop = entry + atr * reg["stop_mult"]
    return round(stop, 6), f"Стоп {reg['stop_mult']:g}×ATR ({reg['label']}) над входом"


def _tp_short(entry: float, stop: float, supports: list[float], fib: list[float], atr: float) -> tuple[float, float | None, str]:
    risk = stop - entry
    min_tp = entry - risk * MIN_RR
    targets = sorted([s for s in supports if s <= min_tp * 1.02] + [f for f in fib if f <= min_tp * 1.02], reverse=True)
    tp1 = targets[0] if targets else entry - risk * MIN_RR
    tp1 = min(tp1, min_tp)
    further = [t for t in targets if t < tp1 * 0.999]
    tp2 = further[0] if further else round(entry - risk * TP2_RR, 6)
    reason = "TP1 у ближайшей поддержки (R:R ≥ 1:2), TP2 — расширение" if targets else f"TP по R:R 1:{MIN_RR:g} (нет уровня ниже)"
    return round(tp1, 6), round(tp2, 6), reason


def zone_stop_take(
    side: str,
    entry: float,
    supports: list[float],
    resistances: list[float],
    fib_prices: list[float],
    atr: float,
    volatility=None,
) -> tuple[float, float]:
    """Стоп/тейк для произвольной точки входа по ЕДИНОЙ методологии с позицией:
    стоп за структурой + буфер ATR (множитель по режиму волатильности),
    тейк у ближайшего уровня с минимумом R:R. Используется и графиком (зоны входа),
    и расчётом позиции, чтобы значения совпадали.
    """
    reg = _regime(volatility)
    if side == "long":
        stop, _ = _stop_long(entry, supports, fib_prices, atr, reg)
        tp, _tp2, _ = _tp_long(entry, stop, resistances, fib_prices, atr)
    else:
        stop, _ = _stop_short(entry, resistances, fib_prices, atr, reg)
        tp, _tp2, _ = _tp_short(entry, stop, supports, fib_prices, atr)
    return round(stop, 6), round(tp, 6)


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
    reg = _regime(analysis.volatility)
    fib_prices = [l.price for l in analysis.fibonacci.levels] if analysis.fibonacci else []

    if side == "long":
        stop, stop_reason = _stop_long(entry, analysis.support_levels, fib_prices, atr, reg)
        tp, tp2, tp_reason = _tp_long(entry, stop, analysis.resistance_levels, fib_prices, atr)
        sl_dist = (entry - stop) / entry * 100
        tp_dist = (tp - entry) / entry * 100
    else:
        stop, stop_reason = _stop_short(entry, analysis.resistance_levels, fib_prices, atr, reg)
        tp, tp2, tp_reason = _tp_short(entry, stop, analysis.support_levels, fib_prices, atr)
        sl_dist = (stop - entry) / entry * 100
        tp_dist = (entry - tp) / entry * 100

    risk = abs(entry - stop)
    reward = abs(tp - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0

    liq = liquidation_price(entry, lev, side)
    liq_dist_pct = None
    stop_before_liq = True
    if liq is not None:
        liq_dist_pct = round(abs(entry - liq) / entry * 100, 2)
        # Стоп должен срабатывать раньше ликвидации.
        stop_before_liq = stop > liq if side == "long" else stop < liq

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
    if liq is not None:
        advice_parts.append(f"⚠ Ликвидация при ${liq:,.4f} ({liq_dist_pct}% от входа)")
        if not stop_before_liq:
            advice_parts.append("🚨 Стоп ЗА ценой ликвидации — позиция ликвидируется раньше стопа, снизьте плечо")
    if abs(pnl_sl) > margin * 0.8:
        advice_parts.append("Стоп >80% маржи — плечо слишком высокое")
    if rr >= MIN_RR:
        advice_parts.append(f"R:R 1:{rr} — фиксируйте 50% на TP1")
    if tp2:
        advice_parts.append(f"TP2: ${tp2:,.4f} (остаток позиции)")
    advice_parts.append("После +1R переведите стоп в безубыток, дальше трейлинг по 1.5×ATR")

    rr_floor = "TP1 у ближайшего реального уровня" if rr >= MIN_RR else "уровень близко — TP по R:R"
    methodology = " · ".join(
        [
            f"Стоп: за структурой + буфер ATR, множитель {reg['stop_mult']:g}×ATR под {reg['label']}",
            f"Тейк: {rr_floor}, минимум R:R 1:{MIN_RR:g}; TP2 — расширение до 1:{TP2_RR:g}",
            "Управление: безубыток после +1R, трейлинг по 1.5×ATR за движением",
        ]
    )

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
        liquidation_price=liq,
        liquidation_distance_pct=liq_dist_pct,
        stop_before_liquidation=stop_before_liq,
        stop_reason=stop_reason,
        tp_reason=tp_reason,
        methodology=methodology,
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
