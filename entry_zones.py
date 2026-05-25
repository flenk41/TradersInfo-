"""Зоны входа LONG (зелёные) и SHORT (красные) для графика."""

from __future__ import annotations


def _zone(price: float, band_pct: float, label: str, kind: str, strength: int) -> dict:
    return {
        "price": round(price, 6),
        "low": round(price * (1 - band_pct), 6),
        "high": round(price * (1 + band_pct), 6),
        "label": label,
        "kind": kind,
        "strength": strength,
    }


def build_entry_zones(
    price: float,
    support_levels: list[float],
    resistance_levels: list[float],
    fib,
    bias,
    trade,
    scalp,
    atr: float,
) -> tuple[list[dict], list[dict]]:
    long_zones: list[dict] = []
    short_zones: list[dict] = []
    if not price or price <= 0:
        price = 1.0
    band = max(0.0008, (atr / price) * 0.35)
    # Риск от точки входа: 1.5×ATR (с полом), тейк по R:R 1:2.
    risk = max(atr * 1.5, price * 0.004)
    rr = 2.0

    def add_long(center: float, label: str, strength: int = 2):
        if center <= 0:
            return
        z = _zone(center, band, label, "long_entry", strength)
        z["stop"] = round(center - risk, 6)
        z["take"] = round(center + risk * rr, 6)
        if not any(abs(z["price"] - x["price"]) / price < band for x in long_zones):
            long_zones.append(z)

    def add_short(center: float, label: str, strength: int = 2):
        if center <= 0:
            return
        z = _zone(center, band, label, "short_entry", strength)
        z["stop"] = round(center + risk, 6)
        z["take"] = round(center - risk * rr, 6)
        if not any(abs(z["price"] - x["price"]) / price < band for x in short_zones):
            short_zones.append(z)

    for i, s in enumerate(support_levels[:3]):
        if s <= price * 1.008:
            add_long(s, f"ЛОНГ у поддержки {i + 1}", 3)

    for i, r in enumerate(resistance_levels[:3]):
        if r >= price * 0.992:
            add_short(r, f"ШОРТ у сопротивления {i + 1}", 3)

    if fib:
        if fib.direction == "ВОСХОДЯЩИЙ" and fib.in_golden_zone:
            mid = (fib.swing_high + fib.swing_low) / 2
            add_long(mid, "ЛОНГ: золотая зона Фибо", 4)
        if fib.direction == "НИСХОДЯЩИЙ" and fib.in_golden_zone:
            mid = (fib.swing_high + fib.swing_low) / 2
            add_short(mid, "ШОРТ: золотая зона Фибо", 4)
        if fib.nearest_support and fib.nearest_support.price < price:
            add_long(fib.nearest_support.price, "ЛОНГ: откат к Фибо", 2)
        if fib.nearest_resistance and fib.nearest_resistance.price > price:
            add_short(fib.nearest_resistance.price, "ШОРТ: откат к Фибо", 2)

    if bias and bias.direction == "long":
        add_long(price * 0.998, "ЛОНГ: откат по bias", 2)
    elif bias and bias.direction == "short":
        add_short(price * 1.002, "ШОРТ: откат по bias", 2)

    if trade:
        if trade.long_score >= 58 and trade.long_score > trade.short_score + 10:
            add_long(price * 0.999, "ЛОНГ: зона входа (оценка)", 3)
        if trade.short_score >= 58 and trade.short_score > trade.long_score + 10:
            add_short(price * 1.001, "ШОРТ: зона входа (оценка)", 3)

    if scalp:
        for sig in scalp.signals:
            if sig.direction == "long" and sig.score >= 40:
                add_long(price * 0.9995, f"Скальп ЛОНГ {sig.timeframe}", 4)
            if sig.direction == "short" and sig.score >= 40:
                add_short(price * 1.0005, f"Скальп ШОРТ {sig.timeframe}", 4)

    if not long_zones and trade and trade.long_score >= 45:
        add_long(price, "ЛОНГ: текущая зона", 1)
    if not short_zones and trade and trade.short_score >= 45:
        add_short(price, "ШОРТ: текущая зона", 1)

    long_zones.sort(key=lambda z: z["strength"], reverse=True)
    short_zones.sort(key=lambda z: z["strength"], reverse=True)
    return long_zones[:4], short_zones[:4]
