"""Технический анализ: тренд, волатильность, уровни."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from market_structure import (
    adx_label,
    calculate_adx,
    detect_structure,
    find_key_levels,
    get_htf_bias,
    volume_confirms_move,
)


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
    market_structure: str = ""
    structure_hint: str = ""
    adx: float = 0.0
    adx_label: str = ""
    volume_confirms: bool = False
    volume_note: str = ""


@dataclass
class MarketBias:
    direction: str
    summary: str
    trade_rule: str


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
    bias: MarketBias | None = None
    timeframes: list[TimeframeAnalysis] = field(default_factory=list)
    volatility: VolatilityMetrics | None = None
    funding: FundingMetrics | None = None
    fibonacci: Any = None
    trade: Any = None
    support_levels: list[float] = field(default_factory=list)
    resistance_levels: list[float] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    bullish_reasons: list[str] = field(default_factory=list)
    bearish_reasons: list[str] = field(default_factory=list)
    support_zones: list[dict] = field(default_factory=list)
    resistance_zones: list[dict] = field(default_factory=list)
    long_entry_zones: list[dict] = field(default_factory=list)
    short_entry_zones: list[dict] = field(default_factory=list)
    market_type: str = "crypto"
    display_name: str = ""
    scalp: Any = None
    deep: Any = None
    accuracy: Any = None


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
    prev2_hist = float(histogram.iloc[-3]) if len(histogram) > 2 else prev_hist

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
    else:
        trend = "Слабо медвежий"

    momentum = "растёт" if hist_val > prev_hist > prev2_hist else "слабеет" if hist_val < prev_hist else "стабилен"

    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": hist_val,
        "trend": trend,
        "cross": cross,
        "momentum": momentum,
    }


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _detect_trend_pro(
    price: float,
    ema20: float,
    ema50: float,
    sma200: float | None,
    structure: str,
    adx: float,
    macd_trend: str,
) -> tuple[str, str]:
    bullish = 0
    bearish = 0

    if "БЫЧ" in structure:
        bullish += 2
    elif "МЕДВ" in structure:
        bearish += 2

    if price > ema20 > ema50:
        bullish += 2
    elif price < ema20 < ema50:
        bearish += 2
    elif price > ema50:
        bullish += 1
    elif price < ema50:
        bearish += 1

    if sma200:
        if price > sma200:
            bullish += 1
        else:
            bearish += 1

    if "БЫЧ" in macd_trend:
        bullish += 1
    elif "МЕДВ" in macd_trend:
        bearish += 1

    if adx < 18:
        return "БОКОВОЙ ↔️", "Флэт (ADX низкий) — не торгуем пробои"

    if bullish >= 4 and bearish <= 1:
        return "БЫЧИЙ 📈", "Сильный" if adx >= 25 else "Умеренный"
    if bearish >= 4 and bullish <= 1:
        return "МЕДВЕЖИЙ 📉", "Сильный" if adx >= 25 else "Умеренный"
    if bullish >= 3:
        return "БЫЧИЙ 📈", "Умеренный"
    if bearish >= 3:
        return "МЕДВЕЖИЙ 📉", "Умеренный"
    return "БОКОВОЙ ↔️", "Смешанные сигналы"


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

    structure, struct_hint = detect_structure(df)
    adx = calculate_adx(df)
    adx_lbl = adx_label(adx)

    trend, strength = _detect_trend_pro(
        price, ema20, ema50, sma200, structure, adx, str(macd_data["trend"])
    )

    vol_ok, vol_note = volume_confirms_move(df, "БЫЧ" in trend)

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
        market_structure=structure,
        structure_hint=struct_hint,
        adx=adx,
        adx_label=adx_lbl,
        volume_confirms=vol_ok,
        volume_note=vol_note,
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
        level, desc = "ВЫСОКАЯ 🔥", "Риск выше нормы — режьте плечо в 2 раза"
    elif atr_percent >= 1.5 or range_24h >= 4:
        level, desc = "СРЕДНЯЯ ⚡", "Нормальный риск — стоп за структурой"
    else:
        level, desc = "НИЗКАЯ 😴", "Тихий рынок — сделки могут застрять в диапазоне"

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
    return find_key_levels(df, price)


def determine_overall_trend(tf_analyses: list[TimeframeAnalysis]) -> tuple[str, str]:
    weights = {"1d": 3, "4h": 2, "1h": 1}
    score = 0.0
    total = 0.0
    for a in tf_analyses:
        w = weights.get(a.timeframe, 1)
        total += w
        if "БЫЧИЙ" in a.trend:
            score += w
        elif "МЕДВЕЖИЙ" in a.trend:
            score -= w

    if total == 0:
        return "СМЕШАННЫЙ ↔️", "Нет данных"

    norm = score / total
    if norm >= 0.55:
        return "БЫЧИЙ 📈", "Старшие ТФ доминируют вверх — приоритет лонгам на откате"
    if norm <= -0.55:
        return "МЕДВЕЖИЙ 📉", "Старшие ТФ доминируют вниз — приоритет шортам на откате"
    return "СМЕШАННЫЙ ↔️", "Нет согласия ТФ — 80% сделок здесь пропускаем"


def build_market_bias(tf_analyses: list[TimeframeAnalysis]) -> MarketBias:
    tf_map = {a.timeframe: a.trend for a in tf_analyses}
    direction, summary = get_htf_bias(tf_map)

    if direction == "long":
        rule = "Покупаем только откаты к поддержке/Фибо 50–61.8%, не покупаем на хаях"
    elif direction == "short":
        rule = "Продаём только откаты к сопротивлению/Фибо, не шортим на лоях"
    else:
        rule = "Cash is a position — ждём совпадения 1D+4H+1H и MACD"

    return MarketBias(direction=direction, summary=summary, trade_rule=rule)


def build_signals(
    tf_analyses: list[TimeframeAnalysis],
    volatility: VolatilityMetrics,
    funding: FundingMetrics | None,
    bias: MarketBias | None,
) -> list[str]:
    signals: list[str] = []

    if bias:
        signals.append(f"Bias: {bias.summary}")
        signals.append(f"Правило: {bias.trade_rule}")

    tf_1d = next((a for a in tf_analyses if a.timeframe == "1d"), None)
    tf_4h = next((a for a in tf_analyses if a.timeframe == "4h"), None)
    tf_1h = next((a for a in tf_analyses if a.timeframe == "1h"), None)

    if tf_1d and tf_1d.adx < 18:
        signals.append(f"1D ADX {tf_1d.adx} — флэт, не торгуем пробои")

    for tf in (tf_1d, tf_4h, tf_1h):
        if not tf:
            continue
        if tf.market_structure:
            signals.append(f"{tf.timeframe.upper()}: {tf.market_structure}")

    if tf_1h:
        if "Бычье" in tf_1h.macd_cross and bias and bias.direction == "long":
            signals.append("MACD 1H: бычий кросс в направлении bias — триггер входа")
        elif "Медвежье" in tf_1h.macd_cross and bias and bias.direction == "short":
            signals.append("MACD 1H: медвежий кросс в направлении bias — триггер входа")
        elif "пересечение" in tf_1h.macd_cross:
            signals.append(f"MACD 1H: {tf_1h.macd_cross} — против bias, не входим")

        if tf_1h.rsi >= 70:
            signals.append(f"RSI 1H {tf_1h.rsi} — перекуплен, лонг только после отката")
        elif tf_1h.rsi <= 30:
            signals.append(f"RSI 1H {tf_1h.rsi} — перепродан, шорт только после отката")

        if not tf_1h.volume_confirms:
            signals.append(f"Объём 1H: {tf_1h.volume_note}")

    if volatility.level.startswith("ВЫСОКАЯ"):
        signals.append("Высокая волатильность — риск 1% на сделку, не 2%")

    if funding:
        if funding.rate_percent > 0.03:
            signals.append("Фандинг против лонга — лонги только по исключению")
        elif funding.rate_percent < -0.03:
            signals.append("Фандинг против шорта — шорты только по исключению")

    return signals
