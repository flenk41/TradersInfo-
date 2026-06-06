"""Балл согласованности сигналов анализа (НЕ вероятность прибыли)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from tis.analysis.analyzer import MarketAnalysis, TimeframeAnalysis
from tis.analysis.entry_advisor import VERDICT_ENTER


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
    checks: list[dict] = field(default_factory=list)


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


def _avg_adx(timeframes: list[TimeframeAnalysis]) -> float:
    vals = [tf.adx for tf in timeframes if getattr(tf, "adx", 0)]
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def _confirmation_checks(analysis: MarketAnalysis, rec_side: str) -> tuple[list[dict], float]:
    """Независимые методы подтверждения. Каждый даёт вклад (delta) в точность."""
    checks: list[dict] = []
    tfs = analysis.timeframes or []
    tf_1h = next((t for t in tfs if t.timeframe == "1h"), None)
    tf_4h = next((t for t in tfs if t.timeframe == "4h"), None)
    directional = rec_side in ("long", "short")

    def add(name, status, delta, detail=""):
        checks.append({"name": name, "status": status, "delta": delta, "detail": detail})

    # 1) Подтверждение объёмом
    if directional:
        vol_ok = any(getattr(t, "volume_confirms", False) for t in (tf_1h, tf_4h) if t)
        if vol_ok:
            note = (tf_1h.volume_note if tf_1h and tf_1h.volume_confirms else (tf_4h.volume_note if tf_4h else ""))
            add("Объём подтверждает движение", "good", 3, note)
        else:
            add("Объём не подтверждает", "bad", -2, "Движение без поддержки объёма")

    # 2) Сила тренда (ADX)
    if directional:
        adx = _avg_adx(tfs)
        if adx >= 25:
            add(f"Сильный тренд (ADX {adx})", "good", 4, "Тренд устойчив — пробои надёжнее")
        elif adx and adx < 18:
            add(f"Флэт (ADX {adx})", "bad", -4, "Боковик — направленные сделки ненадёжны")
        elif adx:
            add(f"Умеренный тренд (ADX {adx})", "neutral", 0, "")

    # 3) RSI — не на экстремуме
    if tf_1h and directional:
        r = tf_1h.rsi
        if rec_side == "long":
            if r >= 72:
                add(f"RSI 1H перегрет ({r})", "bad", -3, "Покупка у вершины — риск отката")
            elif r <= 68:
                add(f"RSI 1H в норме ({r})", "good", 2, "Есть запас по импульсу")
        else:
            if r <= 28:
                add(f"RSI 1H перепродан ({r})", "bad", -3, "Шорт у дна — риск отскока")
            elif r >= 32:
                add(f"RSI 1H в норме ({r})", "good", 2, "Есть запас по импульсу")

    # 4) Дивергенции (из глубокого анализа)
    deep = analysis.deep
    if deep and getattr(deep, "divergences", None) and directional:
        text = " ".join(deep.divergences).lower()
        bull = "быч" in text or "вверх" in text
        bear = "медвеж" in text or "вниз" in text
        first = deep.divergences[0]
        if rec_side == "long" and bull and not bear:
            add("Бычья дивергенция за вход", "good", 3, first)
        elif rec_side == "short" and bear and not bull:
            add("Медвежья дивергенция за вход", "good", 3, first)
        elif (rec_side == "long" and bear) or (rec_side == "short" and bull):
            add("Дивергенция против входа", "bad", -4, first)

    # 5) Режим волатильности
    vol = analysis.volatility
    if vol:
        lvl = (getattr(vol, "level", "") or "").upper()
        if "ВЫСОК" in lvl:
            add("Высокая волатильность", "bad", -3, "Больше шума — стоп шире, сигналы менее точны")
        elif "НИЗК" in lvl:
            add("Низкая волатильность", "neutral", 0, "Спокойный рынок")

    # 6) Запас хода до ближайшего уровня
    price = analysis.price
    if rec_side == "long" and analysis.resistance_levels:
        above = [r for r in analysis.resistance_levels if r > price]
        if above:
            room = (min(above) - price) / price * 100
            if room >= 2:
                add(f"Есть ход до сопротивления (+{room:.1f}%)", "good", 2, "Достаточно места для тейка")
            else:
                add(f"Сопротивление близко (+{room:.1f}%)", "bad", -2, "Мало места для тейка")
    elif rec_side == "short" and analysis.support_levels:
        below = [s for s in analysis.support_levels if s < price]
        if below:
            room = (price - max(below)) / price * 100
            if room >= 2:
                add(f"Есть ход до поддержки (-{room:.1f}%)", "good", 2, "Достаточно места для тейка")
            else:
                add(f"Поддержка близко (-{room:.1f}%)", "bad", -2, "Мало места для тейка")

    total = sum(c["delta"] for c in checks)
    total = round(max(-12.0, min(12.0, float(total))), 1)
    return checks, total


def build_accuracy_metrics(
    analysis: MarketAnalysis,
    klines_4h: pd.DataFrame | None = None,
) -> AccuracyMetrics:
    trade = analysis.trade
    bias = analysis.bias
    deep = analysis.deep

    bias_dir = bias.direction if bias else "neutral"
    # Гейт селективности: направленный вердикт (ПОКУПАТЬ/ПРОДАВАТЬ) выдаём ТОЛЬКО
    # когда лучшая сторона реально «ВХОДИТЬ» (score≥72 + нет блокеров) и явно
    # доминирует. Иначе — «wait». Это режет слабые сетапы и поднимает долю удачных.
    rec_side = "wait"
    if trade:
        best_side = "long" if trade.long_score >= trade.short_score else "short"
        best_verdict = trade.long_verdict if best_side == "long" else trade.short_verdict
        best_side_score = trade.long_score if best_side == "long" else trade.short_score
        spread = abs(trade.long_score - trade.short_score)
        # Фильтры качества (поднимают долю удачных при R:R 1:2):
        #  • высокий балл стороны (≥78) и явный отрыв (≥12) — только сильные сетапы;
        #  • не против HTF-bias — контртренд при тейке 2R чаще выбивает стопом;
        #  • не в глубоком флэте (ADX<18) — в боковике цена редко доходит до 2R.
        # ADX неизвестен (0) — не блокируем (нет данных ≠ флэт).
        avg_adx = _avg_adx(analysis.timeframes)
        not_counter_trend = bias_dir in (best_side, "neutral")
        not_flat = avg_adx == 0 or avg_adx >= 18
        strong = best_side_score >= 78 and spread >= 12
        if best_verdict == VERDICT_ENTER and strong and not_counter_trend and not_flat:
            rec_side = best_side

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

    # Инсайдерский фактор (акции): бычий — за лонг/против шорта, медвежий — наоборот.
    ins = getattr(analysis, "insider", None)
    insider_adj = 0.0
    if ins and ins.get("available") and ins.get("score_adj") and rec_side in ("long", "short"):
        a = float(ins["score_adj"])
        insider_adj = a if rec_side == "long" else -a
        insider_adj = round(max(-8.0, min(8.0, insider_adj)), 1)

    checks, conf_adj = _confirmation_checks(analysis, rec_side)

    overall = round(overall + news_adj + conf_adj + insider_adj, 1)
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
            adj_txt = f" ({'+' if news_adj > 0 else ''}{news_adj} к баллу)"
        factors.append(
            f"Новостной фон ({news['window_days']}д): {news['good']}↑ / {news['bad']}↓ — {news['label']}{adj_txt}"
        )
    if ins and ins.get("available") and ins.get("label"):
        adj_txt = f" ({'+' if insider_adj > 0 else ''}{insider_adj} к баллу)" if insider_adj else ""
        factors.append(f"{ins['label']}: {ins.get('summary', '')}{adj_txt}")

    passed = sum(1 for c in checks if c["status"] == "good")
    expl = (
        f"Балл согласованности {overall}/100 — {label}. "
        f"Подтверждающих методов: {passed}/{len(checks)}. "
        f"Это НЕ вероятность прибыли — это оценка согласия индикаторов, ТФ и недавней истории 4H."
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
        checks=checks,
    )
