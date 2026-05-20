"""Уровни Фибоначчи и зоны входа."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

FIB_RATIOS = {
    "0%": 0.0,
    "23.6%": 0.236,
    "38.2%": 0.382,
    "50%": 0.5,
    "61.8%": 0.618,
    "78.6%": 0.786,
    "100%": 1.0,
}

GOLDEN_ZONE = (0.382, 0.618)


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


def _find_swing_points(df: pd.DataFrame, lookback: int = 80) -> tuple[float, float, str]:
    recent = df.tail(lookback)
    swing_high = float(recent["high"].max())
    swing_low = float(recent["low"].min())
    price = float(recent["close"].iloc[-1])

    mid = (swing_high + swing_low) / 2
    if price >= mid:
        direction = "ВОСХОДЯЩИЙ"
    else:
        direction = "НИСХОДЯЩИЙ"
    return swing_high, swing_low, direction


def _build_levels(swing_high: float, swing_low: float, direction: str) -> list[FibLevel]:
    diff = swing_high - swing_low
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


def _zone_description(
    price: float,
    levels: list[FibLevel],
    direction: str,
    in_golden: bool,
) -> tuple[str, str]:
    sorted_levels = sorted(levels, key=lambda x: x.price)

    for i, lvl in enumerate(sorted_levels):
        if price <= lvl.price:
            if i == 0:
                zone = f"Ниже {lvl.label} (${lvl.price:,.4f})"
            else:
                prev = sorted_levels[i - 1]
                zone = f"Между {prev.label} и {lvl.label}"
            break
    else:
        zone = f"Выше {sorted_levels[-1].label}"

    if in_golden:
        if direction == "ВОСХОДЯЩИЙ":
            hint = "Золотая зона (38.2–61.8%) — классическая зона отката для покупки"
        else:
            hint = "Золотая зона (38.2–61.8%) — классическая зона отката для шорта"
    elif price > sorted_levels[-2].price and direction == "ВОСХОДЯЩИЙ":
        hint = "Цена у верхней границы — не гонитесь за ценой, ждите откат"
    elif price < sorted_levels[1].price and direction == "НИСХОДЯЩИЙ":
        hint = "Цена у нижней границы — риск продолжения падения"
    else:
        hint = "Цена между уровнями — дождитесь подхода к ключевому уровню"

    return zone, hint


def calculate_fibonacci(df: pd.DataFrame, price: float, lookback: int = 80) -> FibonacciAnalysis:
    swing_high, swing_low, direction = _find_swing_points(df, lookback)
    levels = _build_levels(swing_high, swing_low, direction)

    if direction == "ВОСХОДЯЩИЙ":
        fib_382 = swing_high - (swing_high - swing_low) * 0.382
        fib_618 = swing_high - (swing_high - swing_low) * 0.618
        in_golden = fib_618 <= price <= fib_382
        optimal_long = f"${fib_618:,.4f} – ${fib_382:,.4f} (61.8% – 38.2%)"
        optimal_short = f"${fib_382:,.4f} – ${swing_high:,.4f} (38.2% – 0%)"
    else:
        fib_382 = swing_low + (swing_high - swing_low) * 0.382
        fib_618 = swing_low + (swing_high - swing_low) * 0.618
        in_golden = fib_382 <= price <= fib_618
        optimal_long = f"${swing_low:,.4f} – ${fib_382:,.4f} (0% – 38.2%)"
        optimal_short = f"${fib_618:,.4f} – ${fib_382:,.4f} (61.8% – 38.2%)"

    below = [l for l in levels if l.price < price]
    above = [l for l in levels if l.price > price]
    nearest_support = below[-1] if below else None
    nearest_resistance = above[0] if above else None

    current_zone, entry_hint = _zone_description(price, levels, direction, in_golden)

    return FibonacciAnalysis(
        swing_high=round(swing_high, 6),
        swing_low=round(swing_low, 6),
        direction=direction,
        levels=levels,
        current_zone=current_zone,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        in_golden_zone=in_golden,
        entry_hint=entry_hint,
        optimal_long_zone=optimal_long,
        optimal_short_zone=optimal_short,
    )
