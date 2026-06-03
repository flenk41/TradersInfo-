"""Фибоначчи по последнему значимому свингу (пивоты), не min/max."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tis.analysis.market_structure import find_pivot_highs, find_pivot_lows

FIB_RATIOS = {
    "0%": 0.0,
    "23.6%": 0.236,
    "38.2%": 0.382,
    "50%": 0.5,
    "61.8%": 0.618,
    "78.6%": 0.786,
    "100%": 1.0,
}


@dataclass
class FibLevel:
    label: str
    price: float
    ratio: float


@dataclass
class FibonacciAnalysis:
    swing_high: float
    swing_low: float
    direction: str
    levels: list[FibLevel]
    current_zone: str
    nearest_support: FibLevel | None
    nearest_resistance: FibLevel | None
    in_golden_zone: bool
    entry_hint: str
    optimal_long_zone: str
    optimal_short_zone: str


def _last_swing(df: pd.DataFrame) -> tuple[float, float, str, int, int]:
    """Свинг от последнего значимого движения (пивоты + индексы)."""
    highs = find_pivot_highs(df, window=4)
    lows = find_pivot_lows(df, window=4)
    price = float(df["close"].iloc[-1])

    if not highs or not lows:
        recent = df.tail(60)
        return float(recent["high"].max()), float(recent["low"].min()), "ВОСХОДЯЩИЙ", -60, -1

    swing_high = highs[-1]
    swing_low = lows[-1]

    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            direction = "ВОСХОДЯЩИЙ"
        elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            direction = "НИСХОДЯЩИЙ"
        else:
            direction = "ВОСХОДЯЩИЙ" if price >= (swing_high + swing_low) / 2 else "НИСХОДЯЩИЙ"
    else:
        direction = "ВОСХОДЯЩИЙ" if price >= (swing_high + swing_low) / 2 else "НИСХОДЯЩИЙ"

    return swing_high, swing_low, direction, -1, -1


def _build_levels(swing_high: float, swing_low: float, direction: str) -> list[FibLevel]:
    diff = swing_high - swing_low
    if diff <= 0:
        return []
    levels: list[FibLevel] = []

    if direction == "ВОСХОДЯЩИЙ":
        for label, ratio in FIB_RATIOS.items():
            price = swing_high - diff * ratio
            levels.append(FibLevel(label=label, price=round(price, 6), ratio=ratio))
    else:
        for label, ratio in FIB_RATIOS.items():
            price = swing_low + diff * ratio
            levels.append(FibLevel(label=label, price=round(price, 6), ratio=ratio))

    return sorted(levels, key=lambda x: x.price)


def calculate_fibonacci(df: pd.DataFrame, price: float, lookback: int = 80) -> FibonacciAnalysis:
    recent = df.tail(lookback)
    swing_high, swing_low, direction, _, _ = _last_swing(recent)
    levels = _build_levels(swing_high, swing_low, direction)

    if direction == "ВОСХОДЯЩИЙ":
        fib_382 = swing_high - (swing_high - swing_low) * 0.382
        fib_618 = swing_high - (swing_high - swing_low) * 0.618
        in_golden = fib_618 <= price <= fib_382
        optimal_long = f"${fib_618:,.4f} – ${fib_382:,.4f} (откат 61.8–38.2%)"
        optimal_short = f"ниже ${fib_382:,.4f} — только контртренд"
    else:
        fib_382 = swing_low + (swing_high - swing_low) * 0.382
        fib_618 = swing_low + (swing_high - swing_low) * 0.618
        in_golden = fib_382 <= price <= fib_618
        optimal_short = f"${fib_382:,.4f} – ${fib_618:,.4f} (откат 61.8–38.2%)"
        optimal_long = f"выше ${fib_618:,.4f} — только контртренд"

    below = [l for l in levels if l.price < price]
    above = [l for l in levels if l.price > price]
    nearest_support = below[-1] if below else None
    nearest_resistance = above[0] if above else None

    if in_golden:
        hint = "Золотая зона — лучшее место для входа по тренду (подтвердить MACD на 1H)"
    elif direction == "ВОСХОДЯЩИЙ" and price > fib_382:
        hint = "Цена выше 38.2% — не покупайте на эмоциях, ждите откат"
    elif direction == "НИСХОДЯЩИЙ" and price < fib_618:
        hint = "Цена ниже 61.8% — не шортите в панике, ждите откат вверх"
    else:
        hint = "Дождитесь зоны 50–61.8% или пробоя с объёмом"

    zone = f"{'Золотая зона' if in_golden else 'Между уровнями Фибо'} · {direction}"

    return FibonacciAnalysis(
        swing_high=round(swing_high, 6),
        swing_low=round(swing_low, 6),
        direction=direction,
        levels=levels,
        current_zone=zone,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        in_golden_zone=in_golden,
        entry_hint=hint,
        optimal_long_zone=optimal_long,
        optimal_short_zone=optimal_short,
    )
