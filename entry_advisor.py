"""Рекомендации по входу в сделку и вердикт по фандингу."""

from __future__ import annotations

from dataclasses import dataclass

from analyzer import FundingMetrics, TimeframeAnalysis, VolatilityMetrics
from fibonacci import FibonacciAnalysis

VERDICT_ENTER = "ВХОДИТЬ ✅"
VERDICT_WAIT = "ЖДАТЬ ⏳"
VERDICT_NO = "НЕ ВХОДИТЬ ❌"


@dataclass
class FundingVerdict:
    quality: str
    long_action: str
    short_action: str
    long_reason: str
    short_reason: str
    summary: str


@dataclass
class TradeRecommendation:
    long_verdict: str
    short_verdict: str
    long_score: int
    short_score: int
    confidence: str
    best_action: str
    entry_price_hint: str
    stop_loss_hint: str
    take_profit_hint: str
    reasons: list[str]
    warnings: list[str]


def evaluate_funding(funding: FundingMetrics | None) -> FundingVerdict | None:
    if not funding:
        return None

    rate = funding.rate_percent

    if rate >= 0.05:
        quality = "ПЛОХОЙ 🔴"
        long_action = VERDICT_NO
        short_action = VERDICT_ENTER
        long_reason = "Фандинг слишком высокий — лонги переплачивают, рынок перегрет"
        short_reason = "Высокий фандинг поддерживает шорты (лонги платят вам)"
        summary = "Для ЛОНГА входить НЕЛЬЗЯ. Для ШОРТА условия благоприятны."
    elif rate >= 0.02:
        quality = "НЕБЛАГОПРИЯТНЫЙ 🟠"
        long_action = VERDICT_NO
        short_action = VERDICT_WAIT
        long_reason = "Повышенный фандинг — лонги в невыгодной позиции"
        short_reason = "Шорт возможен, но дождитесь подтверждения тренда"
        summary = "ЛОНГ: НЕ ВХОДИТЬ. ШОРТ: осторожно, лучше подождать."
    elif rate <= -0.05:
        quality = "ПЛОХОЙ ДЛЯ ШОРТА 🔴"
        long_action = VERDICT_ENTER
        short_action = VERDICT_NO
        long_reason = "Отрицательный фандинг — шорты переплачивают, возможен squeeze вверх"
        short_reason = "Шортить опасно — рынок перегрет шортами"
        summary = "Для ЛОНГА можно входить. Для ШОРТА входить НЕЛЬЗЯ."
    elif rate <= -0.02:
        quality = "НЕБЛАГОПРИЯТНЫЙ ДЛЯ ШОРТА 🟠"
        long_action = VERDICT_WAIT
        short_action = VERDICT_NO
        long_reason = "Фандинг поддерживает лонги — хорошо, но проверьте тренд"
        short_reason = "Отрицательный фандинг — шорт невыгоден"
        summary = "ЛОНГ: ждать подтверждения. ШОРТ: НЕ ВХОДИТЬ."
    else:
        quality = "НЕЙТРАЛЬНЫЙ 🟢"
        long_action = VERDICT_WAIT
        short_action = VERDICT_WAIT
        long_reason = "Фандинг в норме — не мешает лонгу"
        short_reason = "Фандинг в норме — не мешает шорту"
        summary = "Фандинг нейтральный — решение по тренду и Фибоначчи."

    return FundingVerdict(
        quality=quality,
        long_action=long_action,
        short_action=short_action,
        long_reason=long_reason,
        short_reason=short_reason,
        summary=summary,
    )


def _score_trend(tf_analyses: list[TimeframeAnalysis], side: str) -> tuple[int, list[str]]:
    score = 0
    notes: list[str] = []
    for a in tf_analyses:
        if side == "long":
            if "БЫЧИЙ" in a.trend:
                score += 12
                notes.append(f"{a.timeframe}: бычий тренд (+)")
            elif "МЕДВЕЖИЙ" in a.trend:
                score -= 10
                notes.append(f"{a.timeframe}: медвежий (−)")
        else:
            if "МЕДВЕЖИЙ" in a.trend:
                score += 12
                notes.append(f"{a.timeframe}: медвежий тренд (+)")
            elif "БЫЧИЙ" in a.trend:
                score -= 10
                notes.append(f"{a.timeframe}: бычий (−)")
    return score, notes


def _score_rsi(rsi: float, side: str) -> tuple[int, str | None]:
    if side == "long":
        if 40 <= rsi <= 60:
            return 15, None
        if 30 <= rsi < 40:
            return 8, "RSI низкий — возможен отскок, но тренд слабый"
        if rsi < 30:
            return 5, "RSI перепродан — рискованный лонг без подтверждения"
        if rsi > 70:
            return -25, "RSI перекуплен — лонг опасен"
        if rsi > 60:
            return -8, "RSI высокий — лучше дождаться отката"
    else:
        if 40 <= rsi <= 60:
            return 15, None
        if 60 < rsi <= 70:
            return 8, "RSI высокий — возможен откат вниз"
        if rsi > 70:
            return 5, "RSI перекуплен — шорт рискован без подтверждения"
        if rsi < 30:
            return -25, "RSI перепродан — шорт опасен"
        if rsi < 40:
            return -8, "RSI низкий — лучше дождаться отскока"
    return 0, None


def _score_macd(tf_analyses: list[TimeframeAnalysis], side: str) -> tuple[int, list[str]]:
    score = 0
    notes: list[str] = []
    for a in tf_analyses:
        weight = 14 if a.timeframe == "1h" else 8 if a.timeframe == "4h" else 5
        if side == "long":
            if "Бычье" in a.macd_cross:
                score += weight + 6
                notes.append(f"MACD {a.timeframe}: бычье пересечение (+)")
            elif "БЫЧИЙ" in a.macd_trend:
                score += weight
            elif "Медвежье" in a.macd_cross:
                score -= weight + 4
                notes.append(f"MACD {a.timeframe}: медвежье пересечение (−)")
            elif "МЕДВЕЖИЙ" in a.macd_trend:
                score -= weight
        else:
            if "Медвежье" in a.macd_cross:
                score += weight + 6
                notes.append(f"MACD {a.timeframe}: медвежье пересечение (+)")
            elif "МЕДВЕЖИЙ" in a.macd_trend:
                score += weight
            elif "Бычье" in a.macd_cross:
                score -= weight + 4
                notes.append(f"MACD {a.timeframe}: бычье пересечение (−)")
            elif "БЫЧИЙ" in a.macd_trend:
                score -= weight
    return score, notes[:3]


def _score_fib(fib: FibonacciAnalysis | None, side: str) -> tuple[int, list[str]]:
    if not fib:
        return 0, []
    notes: list[str] = []
    score = 0

    if fib.in_golden_zone:
        if side == "long" and fib.direction == "ВОСХОДЯЩИЙ":
            score += 25
            notes.append("Фибо: золотая зона для лонга (+)")
        elif side == "short" and fib.direction == "НИСХОДЯЩИЙ":
            score += 25
            notes.append("Фибо: золотая зона для шорта (+)")
        else:
            score += 5
            notes.append("Фибо: золотая зона, но направление свинга другое")
    elif side == "long" and fib.direction == "ВОСХОДЯЩИЙ":
        score += 5
    elif side == "short" and fib.direction == "НИСХОДЯЩИЙ":
        score += 5
    else:
        score -= 8
        notes.append("Фибо: цена не в оптимальной зоне входа")

    return score, notes


def _score_funding_side(funding_verdict: FundingVerdict | None, side: str) -> tuple[int, str | None]:
    if not funding_verdict:
        return 0, None
    action = funding_verdict.long_action if side == "long" else funding_verdict.short_action
    if action == VERDICT_ENTER:
        return 20, None
    if action == VERDICT_NO:
        return -30, funding_verdict.long_reason if side == "long" else funding_verdict.short_reason
    return 0, None


def _verdict_from_score(score: int) -> str:
    if score >= 65:
        return VERDICT_ENTER
    if score >= 40:
        return VERDICT_WAIT
    return VERDICT_NO


def build_trade_recommendation(
    tf_analyses: list[TimeframeAnalysis],
    volatility: VolatilityMetrics | None,
    fib: FibonacciAnalysis | None,
    funding_verdict: FundingVerdict | None,
    price: float,
    overall_trend: str,
) -> TradeRecommendation:
    rsi_1h = tf_analyses[0].rsi if tf_analyses else 50.0
    reasons: list[str] = []
    warnings: list[str] = []

    long_score = 50
    short_score = 50

    t_long, notes = _score_trend(tf_analyses, "long")
    long_score += t_long
    reasons.extend(notes[:3])

    t_short, notes = _score_trend(tf_analyses, "short")
    short_score += t_short

    r_long, warn = _score_rsi(rsi_1h, "long")
    long_score += r_long
    if warn:
        warnings.append(warn)

    r_short, warn = _score_rsi(rsi_1h, "short")
    short_score += r_short

    m_long, macd_notes = _score_macd(tf_analyses, "long")
    long_score += m_long
    reasons.extend(macd_notes)

    m_short, _ = _score_macd(tf_analyses, "short")
    short_score += m_short

    f_long, fib_notes = _score_fib(fib, "long")
    long_score += f_long
    reasons.extend(fib_notes)

    f_short, _ = _score_fib(fib, "short")
    short_score += f_short

    fl, wr = _score_funding_side(funding_verdict, "long")
    long_score += fl
    if wr:
        warnings.append(wr)

    fs, wr = _score_funding_side(funding_verdict, "short")
    short_score += fs
    if wr and fs < 0:
        warnings.append(wr)

    if volatility and volatility.level.startswith("ВЫСОКАЯ"):
        long_score -= 10
        short_score -= 10
        warnings.append("Высокая волатильность — уменьшите размер позиции")

    if "СМЕШАННЫЙ" in overall_trend:
        long_score -= 12
        short_score -= 12
        warnings.append("Смешанный тренд — дождитесь ясности на старших ТФ")

    long_score = max(0, min(100, long_score))
    short_score = max(0, min(100, short_score))

    long_verdict = _verdict_from_score(long_score)
    short_verdict = _verdict_from_score(short_score)

    if long_score >= short_score:
        best_action = f"ЛОНГ: {long_verdict}"
        confidence = "высокая" if long_score >= 70 else "средняя" if long_score >= 50 else "низкая"
    else:
        best_action = f"ШОРТ: {short_verdict}"
        confidence = "высокая" if short_score >= 70 else "средняя" if short_score >= 50 else "низкая"

    if fib:
        entry_hint = fib.optimal_long_zone if long_score >= short_score else fib.optimal_short_zone
        entry_price_hint = f"Зона входа: {entry_hint}"
        if fib.nearest_support:
            sl = fib.nearest_support.price * 0.995
            stop_loss_hint = f"Стоп-лосс ниже ${sl:,.4f} ({fib.nearest_support.label})"
        else:
            stop_loss_hint = f"Стоп-лосс ниже ${price * 0.98:,.4f} (~2%)"
        if fib.nearest_resistance:
            tp = fib.nearest_resistance.price
            take_profit_hint = f"Тейк-профит у ${tp:,.4f} ({fib.nearest_resistance.label})"
        else:
            take_profit_hint = f"Тейк-профит у ${price * 1.03:,.4f} (~3%)"
    else:
        entry_price_hint = "Дождитесь подхода к уровню поддержки/сопротивления"
        stop_loss_hint = f"Стоп-лосс: ~2% от ${price:,.4f}"
        take_profit_hint = f"Тейк-профит: ~3% от ${price:,.4f}"

    if funding_verdict:
        if funding_verdict.long_action == VERDICT_NO and long_verdict in (VERDICT_ENTER, VERDICT_WAIT):
            long_verdict = VERDICT_NO
            warnings.append("Фандинг плохой для лонга — НЕ ВХОДИТЬ")
        if funding_verdict.short_action == VERDICT_NO and short_verdict in (VERDICT_ENTER, VERDICT_WAIT):
            short_verdict = VERDICT_NO
            warnings.append("Фандинг плохой для шорта — НЕ ВХОДИТЬ")

    return TradeRecommendation(
        long_verdict=long_verdict,
        short_verdict=short_verdict,
        long_score=long_score,
        short_score=short_score,
        confidence=confidence,
        best_action=best_action,
        entry_price_hint=entry_price_hint,
        stop_loss_hint=stop_loss_hint,
        take_profit_hint=take_profit_hint,
        reasons=reasons[:5],
        warnings=warnings[:4],
    )
