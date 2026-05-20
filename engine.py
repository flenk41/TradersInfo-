"""Основной модуль анализа торговых пар."""

from __future__ import annotations

from analyzer import (
    analyze_funding,
    analyze_timeframe,
    build_signals,
    calculate_volatility,
    determine_overall_trend,
    find_support_resistance,
    MarketAnalysis,
)
from config import DEFAULT_TIMEFRAMES
from data_fetcher import (
    BinanceDataError,
    fetch_funding_rate,
    fetch_klines,
    fetch_open_interest,
    fetch_ticker_24h,
    normalize_symbol,
    validate_symbol,
)
from entry_advisor import build_trade_recommendation, evaluate_funding
from fibonacci import calculate_fibonacci


def _apply_funding_verdict(funding, verdict) -> None:
    if not funding or not verdict:
        return
    funding.quality = verdict.quality
    funding.long_action = verdict.long_action
    funding.short_action = verdict.short_action
    funding.long_reason = verdict.long_reason
    funding.short_reason = verdict.short_reason
    funding.summary = verdict.summary


def analyze_pair(pair: str) -> MarketAnalysis:
    symbol = normalize_symbol(pair)

    if not validate_symbol(symbol):
        raise BinanceDataError(
            f"Пара '{pair}' не найдена на Binance. Пример: ETH/USDT, BTC/USDT"
        )

    ticker = fetch_ticker_24h(symbol)
    price = float(ticker["lastPrice"])

    tf_analyses = []
    klines_1h = None
    klines_4h = None
    for tf in DEFAULT_TIMEFRAMES:
        df = fetch_klines(symbol, interval=tf, limit=250)
        if tf == "1h":
            klines_1h = df
        if tf == "4h":
            klines_4h = df
        tf_analyses.append(analyze_timeframe(df, tf))

    if klines_1h is None:
        klines_1h = fetch_klines(symbol, interval="1h", limit=250)
    if klines_4h is None:
        klines_4h = fetch_klines(symbol, interval="4h", limit=250)

    volatility = calculate_volatility(klines_1h, ticker)
    funding_data = fetch_funding_rate(symbol)
    open_interest = fetch_open_interest(symbol) if funding_data else None
    funding = analyze_funding(funding_data, open_interest)

    funding_verdict = evaluate_funding(funding)
    _apply_funding_verdict(funding, funding_verdict)

    fib = calculate_fibonacci(klines_4h, price)
    support, resistance = find_support_resistance(klines_1h, price)
    overall_trend, trend_summary = determine_overall_trend(tf_analyses)
    rsi_1h = tf_analyses[0].rsi if tf_analyses else 50.0

    trade = build_trade_recommendation(
        tf_analyses=tf_analyses,
        volatility=volatility,
        fib=fib,
        funding_verdict=funding_verdict,
        price=price,
        overall_trend=overall_trend,
    )

    signals = build_signals(tf_analyses, volatility, funding, rsi_1h)
    signals.insert(0, f"ЛОНГ: {trade.long_verdict} (оценка {trade.long_score}/100)")
    signals.insert(1, f"ШОРТ: {trade.short_verdict} (оценка {trade.short_score}/100)")
    if funding and funding.summary:
        signals.insert(2, f"Фандинг: {funding.summary}")
    if fib.in_golden_zone:
        signals.append(f"Фибоначчи: {fib.entry_hint}")

    return MarketAnalysis(
        symbol=symbol,
        price=price,
        change_24h_pct=float(ticker["priceChangePercent"]),
        high_24h=float(ticker["highPrice"]),
        low_24h=float(ticker["lowPrice"]),
        volume_24h=float(ticker["quoteVolume"]),
        overall_trend=overall_trend,
        trend_summary=trend_summary,
        timeframes=tf_analyses,
        volatility=volatility,
        funding=funding,
        fibonacci=fib,
        trade=trade,
        support_levels=support,
        resistance_levels=resistance,
        signals=signals,
    )
