"""Распознавание свечных паттернов на последних свечах ТФ.

Сканируем последние ~24 свечи и для каждой позиции проверяем паттерны,
завершающиеся на ней. Возвращаем найденные с ВРЕМЕНЕМ свечи (unix ts),
направлением (bullish/bearish/neutral) и пояснением. На фронте каждый
рисуется мини-схемой (SVG) и показывает, на какой свече/минуте найден.
"""

from __future__ import annotations

import pandas as pd


def _metrics(o, h, l, c):
    body = abs(c - o)
    rng = h - l if h > l else 1e-9
    upper = h - max(o, c)
    lower = min(o, c) - l
    return body, rng, upper, lower, c >= o


def _p(key, name_ru, name_en, bias, detail_ru, detail_en):
    return {"key": key, "name_ru": name_ru, "name_en": name_en,
            "bias": bias, "detail_ru": detail_ru, "detail_en": detail_en}


def _trend_before(c, i, look=5) -> str:
    """Краткий тренд ДО свечи i (по закрытиям). up/down/flat."""
    j = i - 1
    if j - look < 0 or c[j - look] == 0:
        return "flat"
    diff = (c[j] - c[j - look]) / c[j - look]
    if diff > 0.012:
        return "up"
    if diff < -0.012:
        return "down"
    return "flat"


def _detect_at(o, h, l, c, i) -> list[dict]:
    """Паттерны, завершающиеся на свече i."""
    found: list[dict] = []
    b1, r1, u1, lo1, bull1 = _metrics(o[i], h[i], l[i], c[i])
    trend = _trend_before(c, i)

    # Доджи — крошечное тело при заметном диапазоне
    if b1 <= r1 * 0.1 and r1 > 0:
        found.append(_p("doji", "Доджи", "Doji", "neutral",
                        "Нерешительность рынка — возможен разворот", "Indecision — possible reversal"))
    # Марубозу — тело почти на весь диапазон
    if b1 >= r1 * 0.92:
        if bull1:
            found.append(_p("marubozu_bull", "Бычий марубозу", "Bullish Marubozu", "bullish",
                            "Сильное давление покупателей", "Strong buying pressure"))
        else:
            found.append(_p("marubozu_bear", "Медвежий марубозу", "Bearish Marubozu", "bearish",
                            "Сильное давление продавцов", "Strong selling pressure"))
    # Форма «молот»: маленькое тело сверху, длинная нижняя тень. Смысл зависит от тренда.
    if b1 <= r1 * 0.35 and lo1 >= b1 * 2 and u1 <= b1:
        if trend == "down":
            found.append(_p("hammer", "Молот", "Hammer", "bullish",
                            "Бычий разворот после снижения", "Bullish reversal after a drop"))
        elif trend == "up":
            found.append(_p("hanging_man", "Повешенный", "Hanging Man", "bearish",
                            "Медвежий сигнал на вершине", "Bearish signal at the top"))
    # Форма «звезда»: маленькое тело снизу, длинная верхняя тень.
    if b1 <= r1 * 0.35 and u1 >= b1 * 2 and lo1 <= b1:
        if trend == "up":
            found.append(_p("shooting_star", "Падающая звезда", "Shooting Star", "bearish",
                            "Медвежий разворот после роста", "Bearish reversal after a rise"))
        elif trend == "down":
            found.append(_p("inv_hammer", "Перевёрнутый молот", "Inverted Hammer", "bullish",
                            "Бычий сигнал на дне", "Bullish signal at the bottom"))

    if i - 1 >= 0:
        b2, r2, u2, lo2, bull2 = _metrics(o[i - 1], h[i - 1], l[i - 1], c[i - 1])
        if bull1 and not bull2 and c[i] >= o[i - 1] and o[i] <= c[i - 1] and b1 > b2:
            found.append(_p("engulf_bull", "Бычье поглощение", "Bullish Engulfing", "bullish",
                            "Покупатели перехватили инициативу", "Buyers took control"))
        if not bull1 and bull2 and o[i] >= c[i - 1] and c[i] <= o[i - 1] and b1 > b2:
            found.append(_p("engulf_bear", "Медвежье поглощение", "Bearish Engulfing", "bearish",
                            "Продавцы перехватили инициативу", "Sellers took control"))

    if i - 2 >= 0:
        b2, r2, u2, lo2, bull2 = _metrics(o[i - 1], h[i - 1], l[i - 1], c[i - 1])
        b3, r3, u3, lo3, bull3 = _metrics(o[i - 2], h[i - 2], l[i - 2], c[i - 2])
        mid3 = (o[i - 2] + c[i - 2]) / 2
        big = lambda b, r: b >= r * 0.6
        if not bull3 and b2 <= r2 * 0.4 and bull1 and c[i] > mid3 and b3 > r3 * 0.5:
            found.append(_p("morning_star", "Утренняя звезда", "Morning Star", "bullish",
                            "Сильный бычий разворот (3 свечи)", "Strong bullish reversal (3 candles)"))
        if bull3 and b2 <= r2 * 0.4 and not bull1 and c[i] < mid3 and b3 > r3 * 0.5:
            found.append(_p("evening_star", "Вечерняя звезда", "Evening Star", "bearish",
                            "Сильный медвежий разворот (3 свечи)", "Strong bearish reversal (3 candles)"))
        if bull1 and bull2 and bull3 and big(b1, r1) and big(b2, r2) and c[i] > c[i - 1] > c[i - 2]:
            found.append(_p("three_soldiers", "Три солдата", "Three White Soldiers", "bullish",
                            "Устойчивый рост — три сильных бычьих свечи", "Sustained uptrend — three strong bull candles"))
        if not bull1 and not bull2 and not bull3 and big(b1, r1) and big(b2, r2) and c[i] < c[i - 1] < c[i - 2]:
            found.append(_p("three_crows", "Три вороны", "Three Black Crows", "bearish",
                            "Устойчивое падение — три сильных медвежьих свечи", "Sustained downtrend — three strong bear candles"))
    return found


def detect_patterns(df: pd.DataFrame, scan: int = 24, max_patterns: int = 8) -> list[dict]:
    if df is None or len(df) < 3:
        return []
    o = df["open"].astype(float).tolist()
    h = df["high"].astype(float).tolist()
    l = df["low"].astype(float).tolist()
    c = df["close"].astype(float).tolist()
    times = df["open_time"]
    n = len(c)

    out: list[dict] = []
    seen: set = set()  # дедуп по ТИПУ — показываем каждый паттерн один раз (самый свежий)
    for i in range(n - 1, max(1, n - scan) - 1, -1):
        try:
            ts = int(times.iloc[i].timestamp())
        except Exception:
            ts = 0
        for p in _detect_at(o, h, l, c, i):
            if p["key"] in seen:
                continue
            seen.add(p["key"])
            rec = dict(p)
            rec["time"] = ts
            rec["age"] = n - 1 - i  # 0 = текущая свеча
            out.append(rec)

    out.sort(key=lambda p: p["time"], reverse=True)
    return out[:max_patterns]


# Сила паттерна для прогноза (3 — сильный разворот/продолжение).
_STRENGTH = {
    "morning_star": 3, "evening_star": 3, "three_soldiers": 3, "three_crows": 3,
    "engulf_bull": 3, "engulf_bear": 3, "marubozu_bull": 2, "marubozu_bear": 2,
    "hammer": 2, "shooting_star": 2, "hanging_man": 2, "inv_hammer": 2, "doji": 1,
}


def next_candle_outlook(df: pd.DataFrame, patterns: list[dict]) -> dict:
    """Прогноз следующей свечи по самому свежему сильному паттерну.

    Это эвристика по теории свечного анализа, НЕ гарантия — рынок вероятностен.
    """
    if df is None or len(df) < 1:
        return {}
    last_o = float(df["open"].iloc[-1])
    last_c = float(df["close"].iloc[-1])
    try:
        cur_time = int(df["open_time"].iloc[-1].timestamp())
    except Exception:
        cur_time = 0
    cur_bias = "bullish" if last_c >= last_o else "bearish"

    recent = [p for p in patterns if p.get("age", 99) <= 1]
    if not recent:
        return {"current_time": cur_time, "current_bias": cur_bias,
                "direction": "neutral", "confidence": "low",
                "based_on_key": "", "based_on_ru": "", "based_on_en": ""}

    recent.sort(key=lambda p: (-_STRENGTH.get(p["key"], 1), p.get("age", 0)))
    top = recent[0]
    bias = top["bias"]
    direction = "up" if bias == "bullish" else "down" if bias == "bearish" else "neutral"
    st = _STRENGTH.get(top["key"], 1)
    conf = "high" if st >= 3 else "medium" if st == 2 else "low"
    return {
        "current_time": cur_time, "current_bias": cur_bias,
        "direction": direction, "confidence": conf,
        "based_on_key": top["key"], "based_on_ru": top["name_ru"], "based_on_en": top["name_en"],
    }
