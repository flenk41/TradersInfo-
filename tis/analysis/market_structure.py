"""Структура рынка, пивоты, ADX, объём — как на реальном графике."""

from __future__ import annotations

import numpy as np
import pandas as pd

TF_WEIGHTS = {"1d": 3, "4h": 2, "1h": 1}


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    val = float(adx.iloc[-1])
    return round(val, 2) if not np.isnan(val) else 0.0


def adx_label(adx: float) -> str:
    if adx >= 25:
        return "Сильный тренд 💪"
    if adx >= 18:
        return "Умеренный тренд"
    return "Флэт / шум 📊"


def volume_confirms_move(df: pd.DataFrame, bullish: bool) -> tuple[bool, str]:
    vol = df["volume"].astype(float)
    if len(vol) < 25:
        return False, "Мало данных по объёму"
    recent = vol.iloc[-5:].mean()
    baseline = vol.iloc[-25:-5].mean()
    if baseline <= 0:
        return False, "Объём не подтверждает"
    ratio = recent / baseline
    last_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-6])
    price_up = last_close > prev_close

    if ratio < 0.85:
        return False, "Объём падает — слабое движение"
    if bullish and price_up and ratio >= 1.05:
        return True, f"Объём растёт (+{(ratio - 1) * 100:.0f}%) — покупатели активны"
    if not bullish and not price_up and ratio >= 1.05:
        return True, f"Объём растёт — продавцы активны"
    if ratio >= 1.15:
        return True, "Повышенный объём"
    return False, "Объём нейтральный"


def find_pivot_highs(df: pd.DataFrame, window: int = 5) -> list[float]:
    highs = df["high"].values
    pivots: list[float] = []
    for i in range(window, len(highs) - window):
        if highs[i] == max(highs[i - window : i + window + 1]):
            pivots.append(float(highs[i]))
    return pivots[-4:]


def find_pivot_lows(df: pd.DataFrame, window: int = 5) -> list[float]:
    lows = df["low"].values
    pivots: list[float] = []
    for i in range(window, len(lows) - window):
        if lows[i] == min(lows[i - window : i + window + 1]):
            pivots.append(float(lows[i]))
    return pivots[-4:]


def detect_structure(df: pd.DataFrame) -> tuple[str, str]:
    """HH/HL — бычья структура, LH/LL — медвежья."""
    highs = find_pivot_highs(df)
    lows = find_pivot_lows(df)
    if len(highs) < 2 or len(lows) < 2:
        return "НЕОПРЕДЕЛЁННАЯ", "Недостаточно свингов для структуры"

    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]
    hh, hl = h2 > h1, l2 > l1
    lh, ll = h2 < h1, l2 < l1

    if hh and hl:
        return "БЫЧЬЯ (HH+HL)", "Цена формирует higher high и higher low — торгуем откаты вверх"
    if lh and ll:
        return "МЕДВЕЖЬЯ (LH+LL)", "Lower high и lower low — торгуем откаты вниз"
    if hh and ll:
        return "РАСШИРЕНИЕ", "Волатильный рынок — осторожно с плечом"
    if lh and hl:
        return "СЖАТИЕ", "Возможен пробой — ждите направление"
    return "БОКОВИК", "Структура смешанная — не инициируем сделку"


def find_key_levels(df: pd.DataFrame, price: float) -> tuple[list[float], list[float]]:
    highs = find_pivot_highs(df)
    lows = find_pivot_lows(df)
    supports = sorted({round(v, 6) for v in lows if v < price * 0.999}, reverse=True)[:4]
    resistances = sorted({round(v, 6) for v in highs if v > price * 1.001})[:4]
    return supports, resistances


def get_htf_bias(tf_map: dict[str, str]) -> tuple[str, str]:
    """
    Старший ТФ задаёт направление: 1D > 4H > 1H.
    Возвращает bias: long | short | neutral и описание.
    """
    score = 0
    for tf, weight in TF_WEIGHTS.items():
        trend = tf_map.get(tf, "")
        if "БЫЧ" in trend.upper() or "быч" in trend.lower():
            score += weight
        elif "МЕДВ" in trend.upper() or "медв" in trend.lower():
            score -= weight

    d1 = tf_map.get("1d", "")
    h4 = tf_map.get("4h", "")

    if score >= 3 and "МЕДВ" not in d1.upper():
        return "long", "Старшие ТФ в лонг — ищем покупки на откатах (1D/4H)"
    if score <= -3 and "БЫЧ" not in d1.upper():
        return "short", "Старшие ТФ в шорт — ищем продажи на откатах"
    if "БЫЧ" in d1.upper() and "МЕДВ" in h4.upper():
        return "neutral", "1D бычий, 4H коррекция — ждите подтверждения на 1H"
    if "МЕДВ" in d1.upper() and "БЫЧ" in h4.upper():
        return "neutral", "1D медвежий, 4H отскок — не ловите нож"
    return "neutral", "Нет согласия старших ТФ — пропуск сделки"
