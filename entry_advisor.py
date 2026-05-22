"""Рекомендации по входу — логика опытного трейдера (HTF bias, confluence)."""

from __future__ import annotations

from dataclasses import dataclass

from analyzer import FundingMetrics, MarketBias, TimeframeAnalysis, VolatilityMetrics
from fibonacci import FibonacciAnalysis

VERDICT_ENTER = "ВХОДИТЬ ✅"
VERDICT_WAIT = "ЖДАТЬ ⏳"
VERDICT_NO = "НЕ ВХОДИТЬ ❌"

TF_WEIGHT = {"1d": 3, "4h": 2, "1h": 1}


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

    if rate >= 0.03:
        quality = "ПРОТИВ ЛОНГА 🔴"
        long_action = VERDICT_NO
        short_action = VERDICT_WAIT
        long_reason = "Перегрев лонгов — не покупаем в толпу"
        short_reason = "Фандинг помогает шорту, но нужен тренд"
        summary = "ЛОНГ: НЕ ВХОДИТЬ. ШОРТ: только по тренду."
    elif rate <= -0.03:
        quality = "ПРОТИВ ШОРТА 🔴"
        long_action = VERDICT_WAIT
        short_action = VERDICT_NO
        long_reason = "Шорты переплачивают — возможен вынос вверх"
        short_reason = "Не шортим в перегретые лои"
        summary = "ШОРТ: НЕ ВХОДИТЬ. ЛОНГ: только по тренду."
    elif rate >= 0.01:
        quality = "СЛАБО ПРОТИВ ЛОНГА 🟠"
        long_action = VERDICT_WAIT
        short_action = VERDICT_WAIT
        long_reason = "Фандинг слегка против лонга"
        short_reason = "Нейтрально для шорта"
        summary = "Фандинг не главный — смотрим график."
    elif rate <= -0.01:
        quality = "СЛАБО ПРОТИВ ШОРТА 🟠"
        long_action = VERDICT_WAIT
        short_action = VERDICT_WAIT
        long_reason = "Нейтрально для лонга"
        short_reason = "Фандинг слегка против шорта"
        summary = "Фандинг не главный — смотрим график."
    else:
        quality = "НЕЙТРАЛЬНЫЙ 🟢"
        long_action = VERDICT_WAIT
        short_action = VERDICT_WAIT
        long_reason = "Фандинг не мешает"
        short_reason = "Фандинг не мешает"
        summary = "Фандинг OK — решение за структурой и ТФ."

    return FundingVerdict(
        quality=quality,
        long_action=long_action,
        short_action=short_action,
        long_reason=long_reason,
        short_reason=short_reason,
        summary=summary,
    )


def _get_tf(tf_analyses: list[TimeframeAnalysis], name: str) -> TimeframeAnalysis | None:
    return next((a for a in tf_analyses if a.timeframe == name), None)


def _score_side(
    side: str,
    tf_analyses: list[TimeframeAnalysis],
    bias: MarketBias | None,
    fib: FibonacciAnalysis | None,
    funding_verdict: FundingVerdict | None,
    volatility: VolatilityMetrics | None,
) -> tuple[int, list[str], list[str]]:
    score = 35
    reasons: list[str] = []
    warnings: list[str] = []

    is_long = side == "long"
    tf_1d = _get_tf(tf_analyses, "1d")
    tf_4h = _get_tf(tf_analyses, "4h")
    tf_1h = _get_tf(tf_analyses, "1h")

    if bias:
        if (is_long and bias.direction == "long") or (not is_long and bias.direction == "short"):
            score += 22
            reasons.append(f"HTF bias: {bias.direction} (+)")
        elif bias.direction == "neutral":
            score -= 15
            warnings.append("Нет HTF bias — профи здесь не входят")
        else:
            score -= 28
            warnings.append("Сделка ПРОТИВ старшего ТФ — высокий риск")

    for a in tf_analyses:
        w = TF_WEIGHT.get(a.timeframe, 1) * 5
        if is_long:
            if "БЫЧИЙ" in a.trend:
                score += w
            elif "МЕДВЕЖИЙ" in a.trend:
                score -= w + 3
            if "БЫЧ" in a.market_structure:
                score += 4
            elif "МЕДВ" in a.market_structure:
                score -= 6
        else:
            if "МЕДВЕЖИЙ" in a.trend:
                score += w
            elif "БЫЧИЙ" in a.trend:
                score -= w + 3
            if "МЕДВ" in a.market_structure:
                score += 4
            elif "БЫЧ" in a.market_structure:
                score -= 6

        if a.adx < 18:
            score -= 8 if a.timeframe in ("1d", "4h") else 4
            if a.timeframe == "1d":
                warnings.append(f"1D флэт ADX {a.adx} — только скальп или пропуск")

    if tf_1h:
        rsi = tf_1h.rsi
        if is_long:
            if 45 <= rsi <= 58:
                score += 14
                reasons.append("RSI 1H: здоровый откат для лонга")
            elif 35 <= rsi < 45:
                score += 8
            elif rsi > 68:
                score -= 22
                warnings.append("RSI перекуплен — не гонимся за ценой")
            elif rsi < 28:
                score -= 5
                warnings.append("Перепродан — нужен разворотный паттерн")
        else:
            if 42 <= rsi <= 55:
                score += 14
                reasons.append("RSI 1H: откат для шорта")
            elif 55 < rsi <= 65:
                score += 8
            elif rsi < 32:
                score -= 22
                warnings.append("RSI перепродан — не шортим дно")
            elif rsi > 72:
                score -= 5

        if is_long and "Бычье" in tf_1h.macd_cross and bias and bias.direction == "long":
            score += 18
            reasons.append("MACD 1H: триггер лонга по тренду")
        elif not is_long and "Медвежье" in tf_1h.macd_cross and bias and bias.direction == "short":
            score += 18
            reasons.append("MACD 1H: триггер шорта по тренду")
        elif "пересечение" in tf_1h.macd_cross.lower():
            score -= 10

        if tf_1h.volume_confirms:
            score += 10
            reasons.append(tf_1h.volume_note)
        else:
            score -= 6

    if tf_4h and is_long and "БЫЧ" in tf_4h.macd_trend:
        score += 6
    if tf_4h and not is_long and "МЕДВ" in tf_4h.macd_trend:
        score += 6

    if fib:
        if is_long and fib.direction == "ВОСХОДЯЩИЙ" and fib.in_golden_zone:
            score += 20
            reasons.append("Фибо: золотая зона лонга")
        elif not is_long and fib.direction == "НИСХОДЯЩИЙ" and fib.in_golden_zone:
            score += 20
            reasons.append("Фибо: золотая зона шорта")
        elif is_long and fib.direction == "ВОСХОДЯЩИЙ":
            score += 4
        elif not is_long and fib.direction == "НИСХОДЯЩИЙ":
            score += 4
        else:
            score -= 12
            warnings.append("Фибо не совпадает с направлением сделки")

    if funding_verdict:
        action = funding_verdict.long_action if is_long else funding_verdict.short_action
        if action == VERDICT_NO:
            score -= 35
            warnings.append(funding_verdict.long_reason if is_long else funding_verdict.short_reason)

    if volatility and volatility.level.startswith("ВЫСОКАЯ"):
        score -= 8
        warnings.append("Высокая волатильность — риск 0.5–1% депозита")

    return max(0, min(100, score)), reasons, warnings


def _verdict_from_score(score: int, has_blocker: bool) -> str:
    if has_blocker:
        return VERDICT_NO
    if score >= 72:
        return VERDICT_ENTER
    if score >= 52:
        return VERDICT_WAIT
    return VERDICT_NO


def build_trade_recommendation(
    tf_analyses: list[TimeframeAnalysis],
    volatility: VolatilityMetrics | None,
    fib: FibonacciAnalysis | None,
    funding_verdict: FundingVerdict | None,
    price: float,
    overall_trend: str,
    bias: MarketBias | None = None,
) -> TradeRecommendation:
    long_score, long_reasons, long_warn = _score_side(
        "long", tf_analyses, bias, fib, funding_verdict, volatility
    )
    short_score, short_reasons, short_warn = _score_side(
        "short", tf_analyses, bias, fib, funding_verdict, volatility
    )

    long_block = any("ПРОТИВ старшего" in w for w in long_warn) or (
        funding_verdict and funding_verdict.long_action == VERDICT_NO
    )
    short_block = any("ПРОТИВ старшего" in w for w in short_warn) or (
        funding_verdict and funding_verdict.short_action == VERDICT_NO
    )

    long_verdict = _verdict_from_score(long_score, long_block)
    short_verdict = _verdict_from_score(short_score, short_block)

    if bias and bias.direction == "neutral":
        if long_verdict == VERDICT_ENTER:
            long_verdict = VERDICT_WAIT
        if short_verdict == VERDICT_ENTER:
            short_verdict = VERDICT_WAIT
        long_warn.append("Нет HTF bias — вход только после подтверждения")
        short_warn.append("Нет HTF bias — вход только после подтверждения")

    if long_score >= short_score:
        best_action = f"ЛОНГ: {long_verdict}"
        confidence = "высокая" if long_score >= 78 else "средняя" if long_score >= 60 else "низкая"
    else:
        best_action = f"ШОРТ: {short_verdict}"
        confidence = "высокая" if short_score >= 78 else "средняя" if short_score >= 60 else "низкая"

    if fib:
        if long_score >= short_score:
            entry_price_hint = f"Зона лонга: {fib.optimal_long_zone}"
            if fib.nearest_support:
                sl = fib.nearest_support.price * 0.997
                stop_loss_hint = f"Стоп под {fib.nearest_support.label}: ${sl:,.4f}"
            else:
                stop_loss_hint = "Стоп: 1.5×ATR ниже входа"
            if fib.nearest_resistance:
                take_profit_hint = f"TP1: ${fib.nearest_resistance.price:,.4f} · дальше трейлинг"
            else:
                take_profit_hint = "TP: минимум R:R 1:2.5 от стопа"
        else:
            entry_price_hint = f"Зона шорта: {fib.optimal_short_zone}"
            if fib.nearest_resistance:
                sl = fib.nearest_resistance.price * 1.003
                stop_loss_hint = f"Стоп над {fib.nearest_resistance.label}: ${sl:,.4f}"
            else:
                stop_loss_hint = "Стоп: 1.5×ATR над входом"
            if fib.nearest_support:
                take_profit_hint = f"TP1: ${fib.nearest_support.price:,.4f}"
            else:
                take_profit_hint = "TP: минимум R:R 1:2.5"
    else:
        entry_price_hint = "Вход на откате к EMA50 / уровню"
        stop_loss_hint = "Стоп за последний свинг + буфер ATR"
        take_profit_hint = "Частичная фиксация на 1:2, остаток на 1:3"

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
        reasons=(long_reasons if long_score >= short_score else short_reasons)[:5],
        warnings=(long_warn if long_score >= short_score else short_warn)[:5],
    )
