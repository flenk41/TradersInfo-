"""Причины бычьего и медвежьего рынка — понятный разбор."""

from __future__ import annotations

from analyzer import FundingMetrics, MarketBias, TimeframeAnalysis
from fibonacci import FibonacciAnalysis


def _get_tf(tf_analyses: list[TimeframeAnalysis], name: str) -> TimeframeAnalysis | None:
    return next((a for a in tf_analyses if a.timeframe == name), None)


def build_market_reasons(
    tf_analyses: list[TimeframeAnalysis],
    bias: MarketBias | None,
    funding: FundingMetrics | None,
    fib: FibonacciAnalysis | None,
    overall_trend: str,
    change_24h_pct: float,
) -> tuple[list[str], list[str]]:
    bullish: list[str] = []
    bearish: list[str] = []

    tf_1d = _get_tf(tf_analyses, "1d")
    tf_4h = _get_tf(tf_analyses, "4h")
    tf_1h = _get_tf(tf_analyses, "1h")

    for tf in (tf_1d, tf_4h, tf_1h):
        if not tf:
            continue
        tag = tf.timeframe.upper()
        if "БЫЧИЙ" in tf.trend:
            bullish.append(f"{tag}: тренд бычий ({tf.trend_strength})")
        elif "МЕДВЕЖИЙ" in tf.trend:
            bearish.append(f"{tag}: тренд медвежий ({tf.trend_strength})")
        else:
            bearish.append(f"{tag}: боковик / неопределённость (ADX {tf.adx})")

        if "БЫЧ" in tf.market_structure:
            bullish.append(f"{tag}: структура {tf.market_structure}")
        elif "МЕДВ" in tf.market_structure:
            bearish.append(f"{tag}: структура {tf.market_structure}")
        elif "СЖАТ" in tf.market_structure:
            bearish.append(f"{tag}: сжатие — возможен резкий вынос")

        if "БЫЧ" in tf.macd_trend:
            bullish.append(f"{tag}: MACD бычий (гист. {tf.macd_histogram:+.4f})")
        elif "МЕДВ" in tf.macd_trend:
            bearish.append(f"{tag}: MACD медвежий (гист. {tf.macd_histogram:+.4f})")

        if "Бычье" in tf.macd_cross:
            bullish.append(f"{tag}: MACD бычье пересечение")
        if "Медвежье" in tf.macd_cross:
            bearish.append(f"{tag}: MACD медвежье пересечение")

        if tf.rsi >= 68:
            bearish.append(f"{tag}: RSI {tf.rsi} — перекупленность, риск отката вниз")
        elif tf.rsi <= 32:
            bullish.append(f"{tag}: RSI {tf.rsi} — перепроданность, возможен отскок")
        elif 45 <= tf.rsi <= 58:
            bullish.append(f"{tag}: RSI {tf.rsi} — нейтрально-бычий диапазон")

        if tf.adx < 18:
            bearish.append(f"{tag}: ADX {tf.adx} — слабый тренд, много ложных пробоев")
        elif tf.adx >= 25 and "МЕДВ" in tf.trend:
            bearish.append(f"{tag}: ADX {tf.adx} — сильный медвежий импульс")
        elif tf.adx >= 25 and "БЫЧ" in tf.trend:
            bullish.append(f"{tag}: ADX {tf.adx} — сильный бычий импульс")

        if not tf.volume_confirms and "МЕДВ" in tf.trend:
            bearish.append(f"{tag}: {tf.volume_note}")

    if change_24h_pct < -2:
        bearish.append(f"Цена −{abs(change_24h_pct):.1f}% за 24ч — давление продавцов")
    elif change_24h_pct > 2:
        bullish.append(f"Цена +{change_24h_pct:.1f}% за 24ч — покупатели доминируют")

    if bias:
        if bias.direction == "short":
            bearish.append(f"HTF bias SHORT: {bias.summary}")
        elif bias.direction == "long":
            bullish.append(f"HTF bias LONG: {bias.summary}")
        else:
            bearish.append(f"HTF bias нейтральный: {bias.summary}")

    if funding:
        if funding.rate_percent >= 0.03:
            bearish.append(
                f"Фандинг +{funding.rate_percent:.4f}% — лонги переплачивают, рынок перегрет сверху"
            )
        elif funding.rate_percent <= -0.03:
            bullish.append(
                f"Фандинг {funding.rate_percent:.4f}% — шорты переплачивают, риск squeeze вверх"
            )
        elif funding.rate_percent >= 0.01:
            bearish.append(f"Фандинг слегка положительный (+{funding.rate_percent:.4f}%)")

    if fib:
        if fib.direction == "НИСХОДЯЩИЙ":
            bearish.append(f"Фибо 4H: нисходящий свинг — приоритет продаж на откатах")
        else:
            bullish.append(f"Фибо 4H: восходящий свинг — приоритет покупок на откатах")
        if fib.in_golden_zone and fib.direction == "НИСХОДЯЩИЙ":
            bearish.append("Цена в золотой зоне Фибо — удобный уровень для шорта по тренду")

    if "МЕДВЕЖИЙ" in overall_trend:
        bearish.insert(0, "Итог: преобладает медвежий рынок на старших таймфреймах")
    elif "БЫЧИЙ" in overall_trend:
        bullish.insert(0, "Итог: преобладает бычий рынок на старших таймфреймах")
    else:
        bearish.insert(0, "Итог: смешанный рынок — высокий риск ложных входов")

    bullish = list(dict.fromkeys(bullish))[:12]
    bearish = list(dict.fromkeys(bearish))[:12]
    return bullish, bearish


def levels_to_zones(levels: list[float], kind: str) -> list[dict]:
    """Зоны для прямоугольников на графике (не линии)."""
    band_pct = 0.0018
    label = "Поддержка" if kind == "support" else "Сопротивление"
    zones = []
    for i, price in enumerate(levels):
        zones.append(
            {
                "price": round(price, 6),
                "low": round(price * (1 - band_pct), 6),
                "high": round(price * (1 + band_pct), 6),
                "label": f"{label} {i + 1}",
                "kind": kind,
            }
        )
    return zones
