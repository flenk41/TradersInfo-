"""Оценка точности и согласованности сигналов анализа."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from analyzer import MarketAnalysis, TimeframeAnalysis


@dataclass
class AccuracyMetrics:
    overall_pct: float
    backtest_hit_rate: float
    backtest_samples: int
    timeframe_alignment_pct: float
    indicator_agreement_pct: float
    confidence_grade: str
    reliability_label: str
    recommended_side: str
    explanation: str
    factors: list[str] = field(default_factory=list)


def _trend_direction(trend: str) -> str:
    t = trend.upper()
    if "БЫЧ" in t or "ВОСХ" in t:
        return "long"
    if "МЕДВ" in t or "НИСХ" in t:
        return "short"
    return "neutral"


def _timeframe_alignment(timeframes: list[TimeframeAnalysis], bias_dir: str) -> float:
    if not timeframes:
        return 50.0
    aligned = 0
    for tf in timeframes:
        d = _trend_direction(tf.trend)
        if bias_dir == "long" and d == "long":
            aligned += 1
        elif bias_dir == "short" and d == "short":
            aligned += 1
        elif bias_dir == "neutral" and d == "neutral":
            aligned += 1
    return round(aligned / len(timeframes) * 100, 1)


def _quick_backtest_4h(df: pd.DataFrame) -> tuple[float, int]:
    """Проверка: EMA20/50 + RSI дают направление, совпало ли движение через 3 свечи."""
    if df is None or len(df) < 70:
        return 50.0, 0

    close = df["close"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    hits = 0
    total = 0
    for i in range(55, len(close) - 3):
        if np.isnan(rsi.iloc[i]):
            continue
        bull = ema20.iloc[i] > ema50.iloc[i]
        r = rsi.iloc[i]
        if bull and r < 70:
            pred = "long"
        elif not bull and r > 30:
            pred = "short"
        else:
            continue

        fwd = (close.iloc[i + 3] - close.iloc[i]) / close.iloc[i]
        if pred == "long" and fwd > 0.003:
            hits += 1
        elif pred == "short" and fwd < -0.003:
            hits += 1
        total += 1

    if total < 8:
        return 50.0, total
    return round(hits / total * 100, 1), total


def build_accuracy_metrics(
    analysis: MarketAnalysis,
    klines_4h: pd.DataFrame | None = None,
) -> AccuracyMetrics:
    trade = analysis.trade
    bias = analysis.bias
    deep = analysis.deep

    bias_dir = bias.direction if bias else "neutral"
    if trade and trade.long_score > trade.short_score + 12:
        rec_side = "long"
    elif trade and trade.short_score > trade.long_score + 12:
        rec_side = "short"
    else:
        rec_side = bias_dir if bias_dir != "neutral" else "wait"

    tf_align = _timeframe_alignment(analysis.timeframes, bias_dir)
    bt_rate, bt_n = _quick_backtest_4h(klines_4h)

    long_s = trade.long_score if trade else 50
    short_s = trade.short_score if trade else 50
    best_score = max(long_s, short_s)
    spread = abs(long_s - short_s)

    conf_long = deep.confluence_long if deep else 50
    conf_short = deep.confluence_short if deep else 50
    conf = conf_long if rec_side == "long" else conf_short if rec_side == "short" else (conf_long + conf_short) / 2

    indicator_agreement = round((tf_align + conf + best_score) / 3, 1)

    overall = (
        bt_rate * 0.35 + tf_align * 0.25 + best_score * 0.25 + min(spread * 2, 30) * 0.15
    )

    news = getattr(analysis, "news", None)
    news_adj = 0.0
    if news and news.get("total", 0) >= 3:
        net = news.get("net", 0.0)
        if rec_side == "long":
            news_adj = net * 6
        elif rec_side == "short":
            news_adj = -net * 6
        news_adj = round(max(-6.0, min(6.0, news_adj)), 1)

    overall = round(overall + news_adj, 1)
    overall = max(35.0, min(92.0, overall))

    if overall >= 78 and spread >= 25:
        grade = "A"
        label = "Высокая согласованность"
    elif overall >= 65:
        grade = "B"
        label = "Хорошая надёжность"
    elif overall >= 52:
        grade = "C"
        label = "Средняя — осторожный вход"
    else:
        grade = "D"
        label = "Низкая — лучше подождать"

    factors = [
        f"Согласие таймфреймов: {tf_align}%",
        f"Бэктест 4H (простой): {bt_rate}% на {bt_n} свечах",
        f"Оценка сигнала: {best_score}/100 (разрыв {spread})",
    ]
    if deep:
        factors.append(f"Схождение {rec_side.upper()}: {conf}%")
    if news and news.get("total"):
        adj_txt = ""
        if news_adj:
            adj_txt = f" ({'+' if news_adj > 0 else ''}{news_adj} к точности)"
        factors.append(
            f"Новостной фон ({news['window_days']}д): {news['good']}↑ / {news['bad']}↓ — {news['label']}{adj_txt}"
        )

    expl = (
        f"Сводная точность {overall}% — {label}. "
        f"Это не гарантия прибыли: оценка согласованности индикаторов и недавней истории 4H."
    )

    return AccuracyMetrics(
        overall_pct=overall,
        backtest_hit_rate=bt_rate,
        backtest_samples=bt_n,
        timeframe_alignment_pct=tf_align,
        indicator_agreement_pct=indicator_agreement,
        confidence_grade=grade,
        reliability_label=label,
        recommended_side=rec_side,
        explanation=expl,
        factors=factors,
    )
