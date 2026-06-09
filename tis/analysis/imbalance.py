"""Имбаланс / Fair Value Gap (FVG) — 3-свечной разрыв ликвидности.

Идея (Smart Money / ICT): когда цена движется резко, между фитилями свечи №1 и
свечи №3 остаётся «дыра», которую средняя свеча №2 проскочила. Рынок часто
возвращается, чтобы «залить» этот разрыв — поэтому незаполненные имбалансы
работают как магниты и зоны поддержки/сопротивления.

- Бычий FVG: low[i+1] > high[i-1]  →  зона (high[i-1] … low[i+1]) ниже движения вверх.
- Медвежий FVG: high[i+1] < low[i-1]  →  зона (high[i+1] … low[i-1]) выше движения вниз.

«Заполнен», если последующая свеча полностью прошла зону насквозь.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass
class Imbalance:
    kind: str          # "bullish" | "bearish"
    low: float
    high: float
    mid: float
    price: float       # = mid, для совместимости с отрисовкой зон
    size_pct: float    # размер зоны в % от цены
    distance_pct: float  # удалённость mid от текущей цены (+ выше / − ниже)
    label: str


def find_imbalances(
    df: pd.DataFrame,
    price: float,
    max_zones: int = 4,
    min_size_pct: float = 0.04,
    lookback: int = 120,
) -> list[dict]:
    """Возвращает ближайшие НЕзаполненные имбалансы (зоны) около текущей цены."""
    if df is None or len(df) < 5 or not price or price <= 0:
        return []

    d = df.tail(lookback).reset_index(drop=True)
    highs = d["high"].astype(float).values
    lows = d["low"].astype(float).values
    n = len(d)

    raw: list[dict] = []
    for i in range(1, n - 1):
        h_prev, l_prev = highs[i - 1], lows[i - 1]
        h_next, l_next = highs[i + 1], lows[i + 1]

        if l_next > h_prev:  # бычий разрыв
            low_edge, high_edge, kind = h_prev, l_next, "bullish"
        elif h_next < l_prev:  # медвежий разрыв
            low_edge, high_edge, kind = h_next, l_prev, "bearish"
        else:
            continue

        size_pct = (high_edge - low_edge) / price * 100
        if size_pct < min_size_pct:
            continue

        # Заполнен ли разрыв последующими свечами (прошли насквозь)?
        filled = False
        for j in range(i + 2, n):
            if lows[j] <= low_edge and highs[j] >= high_edge:
                filled = True
                break
            if kind == "bullish" and lows[j] <= low_edge:
                filled = True
                break
            if kind == "bearish" and highs[j] >= high_edge:
                filled = True
                break
        if filled:
            continue

        mid = (low_edge + high_edge) / 2
        raw.append(
            {
                "kind": kind,
                "low": round(low_edge, 6),
                "high": round(high_edge, 6),
                "mid": round(mid, 6),
                "price": round(mid, 6),
                "size_pct": round(size_pct, 2),
                "distance_pct": round((mid - price) / price * 100, 2),
                "label": "Имбаланс ↑" if kind == "bullish" else "Имбаланс ↓",
            }
        )

    # Ближайшие к цене (по модулю удалённости), но не дальше ~12%.
    raw = [z for z in raw if abs(z["distance_pct"]) <= 12]
    raw.sort(key=lambda z: abs(z["distance_pct"]))
    return raw[:max_zones]


def imbalance_summary(zones: list[dict], price: float) -> str:
    if not zones:
        return "Незаполненных имбалансов рядом нет"
    above = [z for z in zones if z["distance_pct"] > 0]
    below = [z for z in zones if z["distance_pct"] <= 0]
    parts = []
    if above:
        nearest = min(above, key=lambda z: z["distance_pct"])
        parts.append(f"сверху {nearest['distance_pct']:+.1f}% (магнит/сопротивление)")
    if below:
        nearest = max(below, key=lambda z: z["distance_pct"])
        parts.append(f"снизу {nearest['distance_pct']:.1f}% (магнит/поддержка)")
    return "Ближайший имбаланс: " + "; ".join(parts)
