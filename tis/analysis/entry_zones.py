"""Зоны входа LONG (зелёные) и SHORT (красные) для графика.

Стоп и тейк для каждой зоны считаются той же функцией, что и для вкладки
позиции (position_calculator.zone_stop_take) — единая методология.
"""

from __future__ import annotations

from tis.analysis.position_calculator import zone_stop_take


def _volume_support(df, price: float, bins: int = 24) -> float | None:
    """Объёмная поддержка ниже цены: уровень с максимальным наторгованным объёмом
    (Volume Profile POC) в зоне ниже текущей цены. Там покупатель исторически
    активен — логичная зона для приблизительного входа в ЛОНГ на откате/отскоке.
    Возвращает цену уровня или None.
    """
    if df is None or len(df) < 20 or not price or price <= 0:
        return None
    try:
        import numpy as np

        h = df["high"].astype(float).values
        l = df["low"].astype(float).values
        c = df["close"].astype(float).values
        v = df["volume"].astype(float).fillna(0).values if hasattr(df["volume"], "fillna") else df["volume"].astype(float).values
        tp = (h + l + c) / 3.0
        lo, hi = float(np.min(l)), float(np.max(h))
        if hi <= lo:
            return None
        edges = np.linspace(lo, hi, bins + 1)
        idx = np.clip(np.digitize(tp, edges) - 1, 0, bins - 1)
        vol_by_bin = np.zeros(bins)
        for i, vol in zip(idx, v):
            vol_by_bin[int(i)] += float(vol)
        centers = (edges[:-1] + edges[1:]) / 2.0
        below = [(centers[i], vol_by_bin[i]) for i in range(bins) if centers[i] < price * 0.999]
        if not below or all(x[1] <= 0 for x in below):
            return None
        return float(max(below, key=lambda x: x[1])[0])
    except Exception:
        return None


def _volume_resistance(df, price: float, bins: int = 24) -> float | None:
    """Объёмное сопротивление ВЫШЕ цены (Volume POC сверху) — зеркало
    `_volume_support` для приблизительного входа в ШОРТ, когда обычных зон нет.
    """
    if df is None or len(df) < 20 or not price or price <= 0:
        return None
    try:
        import numpy as np

        h = df["high"].astype(float).values
        l = df["low"].astype(float).values
        c = df["close"].astype(float).values
        vcol = df["volume"].astype(float)
        v = (vcol.fillna(0).values if hasattr(vcol, "fillna") else vcol.values)
        tp = (h + l + c) / 3.0
        lo, hi = float(np.min(l)), float(np.max(h))
        if hi <= lo:
            return None
        edges = np.linspace(lo, hi, bins + 1)
        idx = np.clip(np.digitize(tp, edges) - 1, 0, bins - 1)
        vol_by_bin = np.zeros(bins)
        for i, vol in zip(idx, v):
            vol_by_bin[int(i)] += float(vol)
        centers = (edges[:-1] + edges[1:]) / 2.0
        above = [(centers[i], vol_by_bin[i]) for i in range(bins) if centers[i] > price * 1.001]
        if not above or all(x[1] <= 0 for x in above):
            return None
        return float(max(above, key=lambda x: x[1])[0])
    except Exception:
        return None


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
    volatility=None,
    df=None,
) -> tuple[list[dict], list[dict]]:
    long_zones: list[dict] = []
    short_zones: list[dict] = []
    if not price or price <= 0:
        price = 1.0
    band = max(0.0008, (atr / price) * 0.35)
    fib_prices = [l.price for l in fib.levels] if fib else []

    def add_long(center: float, label: str, strength: int = 2):
        if center <= 0:
            return
        z = _zone(center, band, label, "long_entry", strength)
        stop, take = zone_stop_take(
            "long", center, support_levels, resistance_levels, fib_prices, atr, volatility
        )
        z["stop"], z["take"] = stop, take
        if not any(abs(z["price"] - x["price"]) / price < band for x in long_zones):
            long_zones.append(z)

    def add_short(center: float, label: str, strength: int = 2):
        if center <= 0:
            return
        z = _zone(center, band, label, "short_entry", strength)
        stop, take = zone_stop_take(
            "short", center, support_levels, resistance_levels, fib_prices, atr, volatility
        )
        z["stop"], z["take"] = stop, take
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

    # Если обычных лонг-зон нет (напр. нисходящий тренд) — даём ПРИБЛИЗИТЕЛЬНЫЙ
    # лонг от объёмной поддержки (Volume POC ниже цены): вероятная зона отскока.
    if not long_zones:
        vs = _volume_support(df, price)
        if vs and vs < price * 0.999:
            add_long(vs, "ЛОНГ (приблизит.): объёмная поддержка", 1)
        elif trade and trade.long_score >= 45:
            add_long(price, "ЛОНГ: текущая зона", 1)
        if long_zones:
            long_zones[-1]["approx"] = True
    if not short_zones:
        vs_r = _volume_resistance(df, price)
        if vs_r and vs_r > price * 1.001:
            add_short(vs_r, "ШОРТ (приблизит.): объёмное сопротивление", 1)
        elif trade and trade.short_score >= 45:
            add_short(price, "ШОРТ: текущая зона", 1)
        if short_zones:
            short_zones[-1]["approx"] = True

    long_zones.sort(key=lambda z: z["strength"], reverse=True)
    short_zones.sort(key=lambda z: z["strength"], reverse=True)
    return long_zones[:4], short_zones[:4]
