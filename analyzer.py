"""Технический анализ: тренд, волатильность, уровни."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class TimeframeAnalysis:
    timeframe: str
    trend: str
    trend_strength: str
    rsi: float
    ema20: float
    ema50: float
    sma200: float | None
    price: float
    change_pct: float
    macd: float
    macd_signal: float
    macd_histogram: float
    macd_trend: str
    macd_cross: str


@dataclass
class VolatilityMetrics:
    atr_14: float
    atr_percent: float
    daily_volatility_pct: float
    range_24h_pct: float
    level: str
    description: str


@dataclass
class FundingMetrics:
    rate: float
    rate_percent: float
    sentiment: str
    next_funding_time: str
    mark_price: float
    index_price: float
    open_interest: float | None = None
    quality: str = ""
    long_action: str = ""
    short_action: str = ""
    long_reason: str = ""
    short_reason: str = ""
    summary: str = ""


@dataclass
class MarketAnalysis:
    symbol: str
    price: float
    change_24h_pct: float
    high_24h: float
    low_24h: float
    volume_24h: float
    overall_trend: str
    trend_summary: str
    timeframes: list[TimeframeAnalysis] = field(default_factory=list)
    volatility: VolatilityMetrics | None = None
    funding: FundingMetrics | None = None
    fibonacci: Any = None
    trade: Any = None
    support_levels: list[float] = field(default_factory=list)
    resistance_levels: list[float] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    return float(value.iloc[-1]) if not np.isnan(value.iloc[-1]) else 50.0


def _calculate_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict[str, float | str]:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal_period)
    histogram = macd_line - signal_line

    macd_val = float(macd_line.iloc[-1])
    signal_val = float(signal_line.iloc[-1])
    hist_val = float(histogram.iloc[-1])
    prev_hist = float(histogram.iloc[-2]) if len(histogram) > 1 else hist_val

    if prev_hist <= 0 < hist_val:
        cross = "Бычье пересечение 🟢"
    elif prev_hist >= 0 > hist_val:
        cross = "Медвежье пересечение 🔴"
    else:
        cross = "Без пересечения"

    if hist_val > 0 and macd_val > signal_val:
        trend = "БЫЧИЙ 📈"
    elif hist_val < 0 and macd_val < signal_val:
        trend = "МЕДВЕЖИЙ 📉"
    elif hist_val > 0:
        trend = "Слабо бычий"
    elif hist_val < 0:
        trend = "Слабо медвежий"
    else:
        trend = "Нейтральный"

    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": hist_val,
        "trend": trend,
        "cross": cross,
    }


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _detect_trend(price: float, ema20: float, ema50: float, sma200: float | None, rsi: float) -> tuple[str, str]:
    bullish = 0
    bearish = 0

    if price > ema20:
        bullish += 1
    else:
        bearish += 1
    if price > ema50:
        bullish += 1
    else:
        bearish += 1
    if sma200 is not None:
        if price > sma200:
            bullish += 1
        else:
            bearish += 1
    if ema20 > ema50:
        bullish += 1
    else:
        bearish += 1
    if rsi > 55:
        bullish += 1
    elif rsi < 45:
        bearish += 1

    if bullish >= 4:
        trend = "БЫЧИЙ 📈"
        strength = "Сильный"
    elif bullish == 3:
        trend = "БЫЧИЙ 📈"
        strength = "Умеренный"
    elif bearish >= 4:
        trend = "МЕДВЕЖИЙ 📉"
        strength = "Сильный"
    elif bearish == 3:
        trend = "МЕДВЕЖИЙ 📉"
        strength = "Умеренный"
    else:
        trend = "БОКОВОЙ ↔️"
        strength = "Неопределённый"

    return trend, strength


def analyze_timeframe(df: pd.DataFrame, timeframe: str) -> TimeframeAnalysis:
    close = df["close"]
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else price
    change_pct = ((price - prev) / prev) * 100 if prev else 0.0

    ema20 = float(_ema(close, 20).iloc[-1])
    ema50 = float(_ema(close, 50).iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    rsi = _rsi(close)
    macd_data = _calculate_macd(close)

    trend, strength = _detect_trend(price, ema20, ema50, sma200, rsi)

    return TimeframeAnalysis(
        timeframe=timeframe,
        trend=trend,
        trend_strength=strength,
        rsi=round(rsi, 2),
        ema20=round(ema20, 4),
        ema50=round(ema50, 4),
        sma200=round(sma200, 4) if sma200 else None,
        price=round(price, 4),
        change_pct=round(change_pct, 2),
        macd=round(float(macd_data["macd"]), 6),
        macd_signal=round(float(macd_data["signal"]), 6),
        macd_histogram=round(float(macd_data["histogram"]), 6),
        macd_trend=str(macd_data["trend"]),
        macd_cross=str(macd_data["cross"]),
    )


def calculate_volatility(df: pd.DataFrame, ticker: dict[str, Any]) -> VolatilityMetrics:
    price = float(df["close"].iloc[-1])
    atr = _atr(df)
    atr_percent = (atr / price) * 100 if price else 0.0

    returns = df["close"].pct_change().dropna()
    daily_vol = float(returns.std() * np.sqrt(24) * 100) if len(returns) > 1 else 0.0

    high_24h = float(ticker.get("highPrice", price))
    low_24h = float(ticker.get("lowPrice", price))
    range_24h = ((high_24h - low_24h) / price) * 100 if price else 0.0

    if atr_percent >= 3 or range_24h >= 8:
        level, desc = "ВЫСОКАЯ 🔥", "Рынок очень активен, повышенный риск"
    elif atr_percent >= 1.5 or range_24h >= 4:
        level, desc = "СРЕДНЯЯ ⚡", "Нормальная активность для крипторынка"
    else:
        level, desc = "НИЗКАЯ 😴", "Спокойный рынок, низкая активность"

    return VolatilityMetrics(
        atr_14=round(atr, 4),
        atr_percent=round(atr_percent, 2),
        daily_volatility_pct=round(daily_vol, 2),
        range_24h_pct=round(range_24h, 2),
        level=level,
        description=desc,
    )


def analyze_funding(data: dict[str, Any] | None, open_interest: float | None) -> FundingMetrics | None:
    if not data:
        return None

    rate = data["rate"]
    rate_pct = data["rate_percent"]

    if rate_pct > 0.05:
        sentiment = "Сильный лонг-перекос (лонги платят шортам)"
    elif rate_pct > 0.01:
        sentiment = "Умеренный лонг-перекос"
    elif rate_pct < -0.05:
        sentiment = "Сильный шорт-перекос (шорты платят лонгам)"
    elif rate_pct < -0.01:
        sentiment = "Умеренный шорт-перекос"
    else:
        sentiment = "Нейтральный (баланс лонгов и шортов)"

    return FundingMetrics(
        rate=rate,
        rate_percent=round(rate_pct, 4),
        sentiment=sentiment,
        next_funding_time=str(data["next_funding_time"]),
        mark_price=round(data["mark_price"], 4),
        index_price=round(data["index_price"], 4),
        open_interest=open_interest,
    )


def find_support_resistance(df: pd.DataFrame, price: float) -> tuple[list[float], list[float]]:
    recent = df.tail(50)
    lows = recent["low"].nsmallest(3).tolist()
    highs = recent["high"].nlargest(3).tolist()

    support = sorted({round(v, 4) for v in lows if v < price}, reverse=True)[:3]
    resistance = sorted({round(v, 4) for v in highs if v > price})[:3]
    return support, resistance


def build_signals(
    tf_analyses: list[TimeframeAnalysis],
    volatility: VolatilityMetrics,
    funding: FundingMetrics | None,
    rsi_1h: float,
) -> list[str]:
    signals: list[str] = []

    trends = [a.trend for a in tf_analyses]
    if all("БЫЧИЙ" in t for t in trends):
        signals.append("Все таймфреймы в бычьем тренде — сильный восходящий импульс")
    elif all("МЕДВЕЖИЙ" in t for t in trends):
        signals.append("Все таймфреймы в медвежьем тренде — давление продавцов")
    elif any("БЫЧИЙ" in t for t in trends) and any("МЕДВЕЖИЙ" in t for t in trends):
        signals.append("Конфликт таймфреймов — возможна коррекция или разворот")

    tf_1h = next((a for a in tf_analyses if a.timeframe == "1h"), tf_analyses[0] if tf_analyses else None)
    if tf_1h:
        if "Бычье" in tf_1h.macd_cross:
            signals.append(f"MACD 1H: бычье пересечение — сигнал на покупку")
        elif "Медвежье" in tf_1h.macd_cross:
            signals.append(f"MACD 1H: медвежье пересечение — сигнал на продажу")
        elif "БЫЧИЙ" in tf_1h.macd_trend:
            signals.append(f"MACD 1H: бычий (гист. {tf_1h.macd_histogram:+.4f})")
        elif "МЕДВЕЖИЙ" in tf_1h.macd_trend:
            signals.append(f"MACD 1H: медвежий (гист. {tf_1h.macd_histogram:+.4f})")

        macd_bull = sum(1 for a in tf_analyses if "БЫЧИЙ" in a.macd_trend or "бычий" in a.macd_trend.lower())
        macd_bear = sum(1 for a in tf_analyses if "МЕДВЕЖИЙ" in a.macd_trend or "медвежий" in a.macd_trend.lower())
        if macd_bull == len(tf_analyses):
            signals.append("MACD бычий на всех ТФ — импульс вверх")
        elif macd_bear == len(tf_analyses):
            signals.append("MACD медвежий на всех ТФ — импульс вниз")

    if rsi_1h >= 70:
        signals.append(f"RSI перекуплен ({rsi_1h}) — риск отката вниз")
    elif rsi_1h <= 30:
        signals.append(f"RSI перепродан ({rsi_1h}) — возможен отскок вверх")

    if volatility.level.startswith("ВЫСОКАЯ"):
        signals.append("Высокая волатильность — используйте стоп-лоссы и уменьшайте плечо")

    if funding:
        if funding.rate_percent > 0.05:
            signals.append("Высокий положительный фандинг — ЛОНГ: НЕ ВХОДИТЬ")
        elif funding.rate_percent < -0.05:
            signals.append("Высокий отрицательный фандинг — ШОРТ: НЕ ВХОДИТЬ")

    return signals


def determine_overall_trend(tf_analyses: list[TimeframeAnalysis]) -> tuple[str, str]:
    scores = []
    for a in tf_analyses:
        if "БЫЧИЙ" in a.trend:
            scores.append(1)
        elif "МЕДВЕЖИЙ" in a.trend:
            scores.append(-1)
        else:
            scores.append(0)

    avg = sum(scores) / len(scores) if scores else 0
    if avg >= 0.6:
        return "БЫЧИЙ 📈", "Преобладает восходящий тренд на большинстве таймфреймов"
    if avg <= -0.6:
        return "МЕДВЕЖИЙ 📉", "Преобладает нисходящий тренд на большинстве таймфреймов"
    return "СМЕШАННЫЙ ↔️", "Тренды на разных таймфреймах расходятся — ждите подтверждения"
