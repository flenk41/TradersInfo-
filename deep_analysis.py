"""Глубокий многофакторный анализ рынка."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from analyzer import FundingMetrics, MarketAnalysis, MarketBias, TimeframeAnalysis, VolatilityMetrics
from fibonacci import FibonacciAnalysis


@dataclass
class IndicatorInsight:
    name: str
    value: str
    signal: str
    detail: str


@dataclass
class Scenario:
    title: str
    probability: str
    trigger: str
    target: str
    action: str


@dataclass
class DeepAnalysis:
    executive_summary: str
    market_regime: str
    regime_description: str
    risk_score: int
    risk_label: str
    confluence_long: int
    confluence_short: int
    confluence_detail: list[str]
    insights: list[IndicatorInsight] = field(default_factory=list)
    divergences: list[str] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    watch_levels: list[str] = field(default_factory=list)
    btc_context: str = ""
    funding_trend: str = ""
    oi_trend: str = ""
    depth_score: int = 0


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _detect_divergence(
    close: pd.Series,
    oscillator: pd.Series,
    lookback: int = 40,
    kind: str = "RSI",
) -> str | None:
    if len(close) < lookback + 5:
        return None
    c = close.tail(lookback).values
    o = oscillator.tail(lookback).values
    mid = lookback // 2
    c1, c2 = c[:mid], c[mid:]
    o1, o2 = o[:mid], o[mid:]

    price_higher = max(c2) > max(c1)
    price_lower = min(c2) < min(c1)
    osc_higher = max(o2) > max(o1)
    osc_lower = min(o2) < min(o1)

    if price_higher and not osc_higher:
        return f"Медвежья дивергенция {kind}: цена выше, {kind} ниже — риск разворота вниз"
    if price_lower and not osc_lower:
        return f"Бычья дивергенция {kind}: цена ниже, {kind} выше — возможен разворот вверх"
    return None


def _bollinger(close: pd.Series, period: int = 20) -> dict:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    price = float(close.iloc[-1])
    u, m, l = float(upper.iloc[-1]), float(mid.iloc[-1]), float(lower.iloc[-1])
    width = (u - l) / m * 100 if m else 0
    prev_width = (float(upper.iloc[-20]) - float(lower.iloc[-20])) / float(mid.iloc[-20]) * 100 if len(close) > 20 else width
    squeeze = width < prev_width * 0.85 and width < 4
    pct_b = (price - l) / (u - l) if u != l else 0.5

    if squeeze:
        signal = "Сжатие (Squeeze) — готовится сильное движение"
    elif pct_b > 0.95:
        signal = "У верхней границы — перекупленность по Боллинджеру"
    elif pct_b < 0.05:
        signal = "У нижней границы — перепроданность по Боллинджеру"
    elif pct_b > 0.6:
        signal = "В верхней половине канала — бычий настрой"
    elif pct_b < 0.4:
        signal = "В нижней половине канала — медвежий настрой"
    else:
        signal = "В середине канала — нейтрально"

    return {
        "upper": u,
        "middle": m,
        "lower": l,
        "width_pct": round(width, 2),
        "pct_b": round(pct_b * 100, 1),
        "signal": signal,
        "squeeze": squeeze,
    }


def _stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> dict:
    low_min = df["low"].rolling(k).min()
    high_max = df["high"].rolling(k).max()
    stoch_k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    stoch_d = stoch_k.rolling(d).mean()
    kv = float(stoch_k.iloc[-1]) if not np.isnan(stoch_k.iloc[-1]) else 50
    dv = float(stoch_d.iloc[-1]) if not np.isnan(stoch_d.iloc[-1]) else 50
    if kv > 80:
        sig = "Перекуплен (Stoch > 80)"
    elif kv < 20:
        sig = "Перепродан (Stoch < 20)"
    elif kv > dv:
        sig = "Stoch растёт — краткосрочный импульс вверх"
    else:
        sig = "Stoch падает — краткосрочный импульс вниз"
    return {"k": round(kv, 1), "d": round(dv, 1), "signal": sig}


def _ema_ribbon(close: pd.Series) -> dict:
    e8 = float(_ema(close, 8).iloc[-1])
    e21 = float(_ema(close, 21).iloc[-1])
    e55 = float(_ema(close, 55).iloc[-1])
    price = float(close.iloc[-1])
    bull_stack = price > e8 > e21 > e55
    bear_stack = price < e8 < e21 < e55
    if bull_stack:
        return {"state": "Бычье выравнивание EMA 8>21>55", "signal": "bull"}
    if bear_stack:
        return {"state": "Медвежье выравнивание EMA 8<21<55", "signal": "bear"}
    return {"state": "EMA переплетены — нет чёткого тренда", "signal": "neutral"}


def _funding_trend_text(points: list[dict]) -> str:
    if len(points) < 5:
        return "Недостаточно истории фандинга"
    vals = [p["value"] for p in points[-12:]]
    avg_old = sum(vals[:6]) / 6
    avg_new = sum(vals[6:]) / 6
    if avg_new > avg_old + 0.005:
        return f"Фандинг растёт ({avg_new:+.4f}% vs {avg_old:+.4f}%) — лонги платят больше, рынок перегревается"
    if avg_new < avg_old - 0.005:
        return f"Фандинг падает ({avg_new:+.4f}% vs {avg_old:+.4f}%) — шорты отступают, поддержка лонгов"
    return f"Фандинг стабилен (~{avg_new:+.4f}%) — без экстремумов"


def _oi_trend_text(history: list[dict]) -> str:
    if len(history) < 5:
        return "Open Interest: данных мало"
    vals = [h["sumOpenInterest"] for h in history]
    chg = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] else 0
    if chg > 8:
        return f"OI +{chg:.1f}% — в рынок заходят новые позиции (рост интереса)"
    if chg < -8:
        return f"OI {chg:.1f}% — закрытие позиций, слабее conviction"
    return f"OI стабилен ({chg:+.1f}%) — без притока капитала"


def _btc_context(symbol: str, btc_change_24h: float | None, asset_change: float) -> str:
    if symbol.startswith("BTC") or btc_change_24h is None:
        return ""
    diff = asset_change - btc_change_24h
    if diff > 2:
        return f"Актив сильнее BTC на {diff:.1f}% — относительная сила (outperformance)"
    if diff < -2:
        return f"Актив слабее BTC на {abs(diff):.1f}% — относительная слабость"
    return "Движение в ногу с BTC — смотрите общий крипторынок"


def _market_regime(
    tf_4h: TimeframeAnalysis | None,
    volatility: VolatilityMetrics | None,
) -> tuple[str, str]:
    adx = tf_4h.adx if tf_4h else 0
    if volatility and volatility.level.startswith("ВЫСОКАЯ"):
        return "ВОЛАТИЛЬНЫЙ", "Расширенные стопы, меньший размер, только по тренду"
    if adx >= 25 and tf_4h and "БЫЧ" in tf_4h.trend:
        return "ТРЕНД ВВЕРХ", "Торгуем откаты в лонг, шорт только скальп"
    if adx >= 25 and tf_4h and "МЕДВ" in tf_4h.trend:
        return "ТРЕНД ВНИЗ", "Торгуем откаты в шорт, лонг только скальп"
    if adx < 18:
        return "ФЛЭТ", "Пробои часто ложные — торгуйте от границ или ждите"
    return "ПЕРЕХОДНЫЙ", "Смешанные сигналы — снижайте частоту сделок"


def _build_scenarios(
    price: float,
    support: list[float],
    resistance: list[float],
    bias: MarketBias | None,
    fib: FibonacciAnalysis | None,
    atr: float,
) -> list[Scenario]:
    scenarios: list[Scenario] = []
    sup = support[0] if support else price - atr * 2
    res = resistance[0] if resistance else price + atr * 2

    if bias and bias.direction == "long":
        scenarios.append(
            Scenario(
                title="Базовый (бычий)",
                probability="45%",
                trigger="Удержание поддержки + MACD 1H вверх",
                target=f"${res:,.2f}",
                action="Лонг на откате к зоне 50–61.8% Фибо",
            )
        )
        scenarios.append(
            Scenario(
                title="Медвежий сценарий",
                probability="25%",
                trigger=f"Пробой ниже ${sup:,.2f}",
                target=f"${sup - atr:,.2f}",
                action="Выход из лонга / шорт с подтверждением",
            )
        )
    elif bias and bias.direction == "short":
        scenarios.append(
            Scenario(
                title="Базовый (медвежий)",
                probability="45%",
                trigger="Откат к сопротивлению + отказ",
                target=f"${sup:,.2f}",
                action="Шорт от зоны сопротивления / Фибо",
            )
        )
        scenarios.append(
            Scenario(
                title="Бычий сценарий",
                probability="25%",
                trigger=f"Пробой выше ${res:,.2f}",
                target=f"${res + atr:,.2f}",
                action="Закрыть шорт, не ловить разворот сразу",
            )
        )
    else:
        scenarios.append(
            Scenario(
                title="Диапазон",
                probability="50%",
                trigger=f"Цена между ${sup:,.2f} и ${res:,.2f}",
                target="Границы диапазона",
                action="Покупка у низа / продажа у верха, малый размер",
            )
        )

    if fib and fib.in_golden_zone:
        scenarios.append(
            Scenario(
                title="Откат по Фибо",
                probability="35%",
                trigger="Золотая зона 38.2–61.8%",
                target=f"{'$' + format(res, ',.2f') if bias and bias.direction == 'long' else '$' + format(sup, ',.2f')}",
                action=fib.entry_hint[:80],
            )
        )

    return scenarios[:4]


def build_deep_analysis(
    analysis: MarketAnalysis,
    klines_1h: pd.DataFrame,
    klines_4h: pd.DataFrame,
    funding_history: list[dict] | None = None,
    oi_history: list[dict] | None = None,
    btc_change_24h: float | None = None,
) -> DeepAnalysis:
    price = analysis.price
    tf_1h = next((t for t in analysis.timeframes if t.timeframe == "1h"), None)
    tf_4h = next((t for t in analysis.timeframes if t.timeframe == "4h"), None)
    tf_1d = next((t for t in analysis.timeframes if t.timeframe == "1d"), None)
    vol = analysis.volatility
    atr = vol.atr_14 if vol else price * 0.02

    insights: list[IndicatorInsight] = []
    divergences: list[str] = []
    confluence_detail: list[str] = []
    long_pts = 0
    short_pts = 0

    for label, df in [("1H", klines_1h), ("4H", klines_4h)]:
        close = df["close"]
        rsi_s = _rsi_series(close)
        div_rsi = _detect_divergence(close, rsi_s, kind=f"RSI {label}")
        if div_rsi:
            divergences.append(div_rsi)
            if "Бычья" in div_rsi:
                long_pts += 2
            else:
                short_pts += 2

        ema12 = _ema(close, 12)
        ema26 = _ema(close, 26)
        macd_line = ema12 - ema26
        div_macd = _detect_divergence(close, macd_line, kind=f"MACD {label}")
        if div_macd:
            divergences.append(div_macd)

        bb = _bollinger(close)
        insights.append(
            IndicatorInsight(
                name=f"Bollinger {label}",
                value=f"Ширина {bb['width_pct']}% · %B={bb['pct_b']}",
                signal=bb["signal"],
                detail=f"Верх ${bb['upper']:,.2f} · Низ ${bb['lower']:,.2f}",
            )
        )
        if bb["squeeze"]:
            confluence_detail.append(f"{label}: сжатие Боллинджера — ждите пробой")

        st = _stochastic(df)
        insights.append(
            IndicatorInsight(
                name=f"Stochastic {label}",
                value=f"K={st['k']} D={st['d']}",
                signal=st["signal"],
                detail="",
            )
        )

        ribbon = _ema_ribbon(close)
        insights.append(
            IndicatorInsight(
                name=f"EMA Ribbon {label}",
                value=ribbon["state"],
                signal=ribbon["signal"],
                detail="",
            )
        )
        if ribbon["signal"] == "bull":
            long_pts += 1
        elif ribbon["signal"] == "bear":
            short_pts += 1

    if tf_1d:
        if "БЫЧ" in tf_1d.trend:
            long_pts += 3
            confluence_detail.append("1D: бычий тренд (+3)")
        elif "МЕДВ" in tf_1d.trend:
            short_pts += 3
            confluence_detail.append("1D: медвежий тренд (+3)")
    if tf_4h:
        if "БЫЧ" in tf_4h.trend:
            long_pts += 2
        elif "МЕДВ" in tf_4h.trend:
            short_pts += 2
    if tf_1h:
        if "Бычье" in tf_1h.macd_cross:
            long_pts += 2
        if "Медвежье" in tf_1h.macd_cross:
            short_pts += 2

    if analysis.bias:
        if analysis.bias.direction == "long":
            long_pts += 3
        elif analysis.bias.direction == "short":
            short_pts += 3

    if analysis.fibonacci and analysis.fibonacci.in_golden_zone:
        if analysis.fibonacci.direction == "ВОСХОДЯЩИЙ":
            long_pts += 2
        else:
            short_pts += 2

    funding_trend = _funding_trend_text(funding_history or [])
    oi_trend = _oi_trend_text(oi_history or [])
    btc_ctx = _btc_context(analysis.symbol, btc_change_24h, analysis.change_24h_pct)

    regime, regime_desc = _market_regime(tf_4h, vol)

    max_pts = 15
    confluence_long = min(100, int(long_pts / max_pts * 100))
    confluence_short = min(100, int(short_pts / max_pts * 100))

    risk = 50
    if vol and vol.level.startswith("ВЫСОКАЯ"):
        risk += 25
    if divergences:
        risk += 10
    if analysis.bias and analysis.bias.direction == "neutral":
        risk += 15
    if tf_1d and tf_1d.adx >= 25:
        risk -= 10
    risk = max(10, min(95, risk))
    risk_label = "Низкий" if risk < 35 else "Средний" if risk < 60 else "Высокий"

    watch: list[str] = []
    for r in analysis.resistance_levels[:3]:
        watch.append(f"Сопротивление ${r:,.4f} — пробой = бычий импульс")
    for s in analysis.support_levels[:3]:
        watch.append(f"Поддержка ${s:,.4f} — пробой = медвежье ускорение")
    if analysis.funding:
        watch.append(f"След. фандинг: {str(analysis.funding.next_funding_time)[:16]}")

    scenarios = _build_scenarios(
        price,
        analysis.support_levels,
        analysis.resistance_levels,
        analysis.bias,
        analysis.fibonacci,
        atr,
    )

    trade = analysis.trade
    summary_parts = [
        f"{analysis.symbol}: {analysis.overall_trend}, режим {regime}.",
        analysis.trend_summary,
    ]
    if analysis.bias:
        summary_parts.append(analysis.bias.summary)
    if trade:
        summary_parts.append(
            f"Рекомендация: {trade.best_action}. Лонг {trade.long_score}/100, шорт {trade.short_score}/100."
        )
    if divergences:
        summary_parts.append(f"Ключевое: {divergences[0]}")
    executive = " ".join(summary_parts)

    depth = min(
        100,
        40
        + len(insights)
        + len(divergences) * 8
        + len(analysis.bullish_reasons)
        + len(analysis.bearish_reasons),
    )

    return DeepAnalysis(
        executive_summary=executive,
        market_regime=regime,
        regime_description=regime_desc,
        risk_score=risk,
        risk_label=risk_label,
        confluence_long=confluence_long,
        confluence_short=confluence_short,
        confluence_detail=confluence_detail,
        insights=insights,
        divergences=divergences or ["Дивергенций не обнаружено — тренд без скрытого разворота"],
        scenarios=scenarios,
        watch_levels=watch,
        btc_context=btc_ctx,
        funding_trend=funding_trend,
        oi_trend=oi_trend,
        depth_score=depth,
    )
