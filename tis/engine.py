"""Основной модуль анализа торговых пар."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from tis.analysis.analyzer import (
    _atr,
    analyze_funding,
    analyze_timeframe,
    build_market_bias,
    build_signals,
    calculate_volatility,
    determine_overall_trend,
    find_support_resistance,
    MarketAnalysis,
)
from tis.core.config import DEFAULT_TIMEFRAMES, SCALP_TIMEFRAMES
from tis.analysis.deep_analysis import build_deep_analysis
from tis.analysis.entry_advisor import build_trade_recommendation, evaluate_funding
from tis.analysis.entry_zones import build_entry_zones
from tis.analysis.fibonacci import calculate_fibonacci
from tis.data.market_data import (
    fetch_btc_change_24h,
    fetch_funding_history,
    fetch_klines,
    fetch_ticker_24h,
    get_funding_rate,
    get_open_interest,
    get_open_interest_history,
    validate_symbol,
)
from tis.analysis.market_reasons import build_market_reasons, levels_to_zones
from tis.analysis.market_structure import find_key_levels
from tis.core.markets import MarketDataError, detect_market, normalize_pair
from tis.analysis.accuracy_estimator import build_accuracy_metrics
from tis.analysis.scalping import build_scalping_analysis


def _apply_funding_verdict(funding, verdict) -> None:
    if not funding or not verdict:
        return
    funding.quality = verdict.quality
    funding.long_action = verdict.long_action
    funding.short_action = verdict.short_action
    funding.long_reason = verdict.long_reason
    funding.short_reason = verdict.short_reason
    funding.summary = verdict.summary


def cached_analysis(pair: str, market: str | None = None, source: str | None = None) -> "MarketAnalysis":
    """Анализ через тот же кэш, что и эндпоинт /api/analyze.

    Ключ совпадает с web_app (`analyze:{market|auto}:{PAIR}`), поэтому балл
    согласованности в скринере и в Обзоре берётся из ОДНОГО результата —
    числа идентичны, а клик по инструменту после скринера почти мгновенный
    (результат уже в кэше). TTL общий (data_cache, 50с).
    """
    from tis.core.data_cache import get_cached

    src = (source or "").strip().lower()
    key = f"analyze:{market or 'auto'}:{src or 'def'}:{pair.upper()}"
    return get_cached(key, lambda: analyze_pair(pair, market=market, source=source))


def analyze_pair(pair: str, market: str | None = None, source: str | None = None) -> MarketAnalysis:
    m = detect_market(pair, market)
    symbol, display = normalize_pair(pair, m)

    # Источник крипто-данных: "bybit" → публичный Bybit V5, иначе авто (Binance→Yahoo).
    src = (source or "").strip().lower() if m == "crypto" else None

    # Тикер сам по себе валидирует инструмент — отдельный validate_symbol не делаем,
    # чтобы не дублировать сетевой запрос (особенно к MOEX/Yahoo).
    try:
        ticker = fetch_ticker_24h(pair, m, source=src)
        price = float(ticker["lastPrice"])
    except MarketDataError:
        raise
    except Exception:
        raise MarketDataError(
            f"Инструмент '{pair}' не найден. Примеры: BTC/USDT, AAPL, EUR/USD"
        )
    if price <= 0:
        raise MarketDataError(
            f"Инструмент '{pair}' не найден. Примеры: BTC/USDT, AAPL, EUR/USD"
        )

    klines_map: dict[str, object] = {}
    intervals = [
        *[(tf, 250) for tf in DEFAULT_TIMEFRAMES],
        *[(tf, 120) for tf in SCALP_TIMEFRAMES],
    ]

    def _load(interval: str, limit: int):
        return fetch_klines(pair, interval=interval, limit=limit, market=m, source=src)

    with ThreadPoolExecutor(max_workers=min(6, len(intervals))) as pool:
        futures = {pool.submit(_load, tf, lim): tf for tf, lim in intervals}
        for fut in as_completed(futures):
            tf = futures[fut]
            try:
                klines_map[tf] = fut.result()
            except Exception:
                pass

    klines_1h = klines_map.get("1h")
    klines_4h = klines_map.get("4h")
    klines_5m = klines_map.get("5m")
    klines_15m = klines_map.get("15m")

    if klines_1h is None:
        klines_1h = fetch_klines(pair, interval="1h", limit=250, market=m, source=src)
    if klines_4h is None:
        klines_4h = fetch_klines(pair, interval="4h", limit=250, market=m, source=src)

    tf_analyses = []
    for tf in DEFAULT_TIMEFRAMES:
        df = klines_map.get(tf)
        if df is not None:
            tf_analyses.append(analyze_timeframe(df, tf))

    volatility = calculate_volatility(klines_1h, ticker)
    funding_data = get_funding_rate(pair, m, source=src)
    open_interest = get_open_interest(pair, m, source=src) if funding_data else None
    funding = analyze_funding(funding_data, open_interest)

    funding_verdict = evaluate_funding(funding)
    _apply_funding_verdict(funding, funding_verdict)

    fib = calculate_fibonacci(klines_4h, price)
    support_4h, resist_4h = find_key_levels(klines_4h, price)
    support_1h, resist_1h = find_support_resistance(klines_1h, price)
    support = sorted(set(support_4h + support_1h), reverse=True)[:4]
    resistance = sorted(set(resist_4h + resist_1h))[:4]

    if fib:
        if fib.nearest_support and fib.nearest_support.price not in support:
            support.append(fib.nearest_support.price)
        if fib.swing_low and fib.swing_low < price and fib.swing_low not in support:
            support.append(fib.swing_low)
        if fib.nearest_resistance and fib.nearest_resistance.price not in resistance:
            resistance.append(fib.nearest_resistance.price)
    support = sorted(set(support), reverse=True)[:4]
    resistance = sorted(set(resistance))[:4]

    overall_trend, trend_summary = determine_overall_trend(tf_analyses)
    bias = build_market_bias(tf_analyses)

    trade = build_trade_recommendation(
        tf_analyses=tf_analyses,
        volatility=volatility,
        fib=fib,
        funding_verdict=funding_verdict,
        price=price,
        overall_trend=overall_trend,
        bias=bias,
    )

    atr = volatility.atr_14 if volatility else price * 0.02
    scalp = build_scalping_analysis(klines_5m, klines_15m, price, atr)

    # Зоны входа и имбалансы для каждого ТФ: масштабируются под таймфрейм
    # (на 5m уже, на 1D шире). Данные по ТФ уже загружены — без новых запросов.
    from tis.analysis.imbalance import find_imbalances, imbalance_summary
    from tis.analysis.candle_patterns import detect_patterns, next_candle_outlook

    entry_zones_by_tf: dict = {}
    imbalances_by_tf: dict = {}
    patterns_by_tf: dict = {}
    pattern_outlook_by_tf: dict = {}
    for tf_key in ("5m", "15m", "1h", "4h", "1d"):
        df_tf = klines_map.get(tf_key)
        if df_tf is None or len(df_tf) < 20:
            continue
        try:
            atr_tf = _atr(df_tf)
        except Exception:
            continue
        if not atr_tf or atr_tf <= 0:
            continue
        lz, sz = build_entry_zones(price, support, resistance, fib, bias, trade, scalp, atr_tf, volatility, df=df_tf)
        entry_zones_by_tf[tf_key] = {"long": lz, "short": sz}
        try:
            imbalances_by_tf[tf_key] = find_imbalances(df_tf, price)
        except Exception:
            imbalances_by_tf[tf_key] = []
        try:
            pats = detect_patterns(df_tf)
            patterns_by_tf[tf_key] = pats
            pattern_outlook_by_tf[tf_key] = next_candle_outlook(df_tf, pats)
        except Exception:
            patterns_by_tf[tf_key] = []
            pattern_outlook_by_tf[tf_key] = {}

    default_zones = entry_zones_by_tf.get("1h")
    if default_zones:
        long_entry, short_entry = default_zones["long"], default_zones["short"]
    else:
        long_entry, short_entry = build_entry_zones(
            price, support, resistance, fib, bias, trade, scalp, atr, volatility,
            df=klines_map.get("1h") or klines_map.get("4h"),
        )

    signals = build_signals(tf_analyses, volatility, funding, bias)
    signals.insert(0, f"ЛОНГ: {trade.long_verdict} ({trade.long_score}/100)")
    signals.insert(1, f"ШОРТ: {trade.short_verdict} ({trade.short_score}/100)")
    if funding and funding.summary:
        signals.insert(2, funding.summary)
    signals.append(scalp.verdict)

    bullish_reasons, bearish_reasons = build_market_reasons(
        tf_analyses, bias, funding, fib, overall_trend, float(ticker["priceChangePercent"])
    )
    support_zones = levels_to_zones(support, "support")
    resistance_zones = levels_to_zones(resistance, "resistance")

    funding_hist: list = []
    oi_hist: list = []
    btc_chg = None
    if m == "crypto":

        def _fund():
            return fetch_funding_history(pair, limit=90, market=m, source=src)

        def _oi():
            return get_open_interest_history(pair, m, source=src)

        def _btc():
            return fetch_btc_change_24h()

        with ThreadPoolExecutor(max_workers=3) as pool:
            f_fund = pool.submit(_fund)
            f_oi = pool.submit(_oi)
            f_btc = (
                pool.submit(_btc) if not symbol.startswith("BTC") else None
            )
            funding_hist = f_fund.result()
            oi_hist = f_oi.result()
            if f_btc:
                try:
                    btc_chg = f_btc.result()
                except Exception:
                    btc_chg = None

    partial = MarketAnalysis(
        symbol=symbol,
        display_name=display,
        market_type=m,
        price=price,
        change_24h_pct=float(ticker["priceChangePercent"]),
        high_24h=float(ticker["highPrice"]),
        low_24h=float(ticker["lowPrice"]),
        volume_24h=float(ticker["quoteVolume"]),
        overall_trend=overall_trend,
        trend_summary=trend_summary,
        bias=bias,
        timeframes=tf_analyses,
        volatility=volatility,
        funding=funding,
        fibonacci=fib,
        trade=trade,
        scalp=scalp,
        support_levels=support,
        resistance_levels=resistance,
        signals=signals,
        bullish_reasons=bullish_reasons,
        bearish_reasons=bearish_reasons,
        support_zones=support_zones,
        resistance_zones=resistance_zones,
        long_entry_zones=long_entry,
        short_entry_zones=short_entry,
        entry_zones_by_tf=entry_zones_by_tf,
        imbalances=imbalances_by_tf.get("1h", []),
        imbalances_by_tf=imbalances_by_tf,
        imbalance_summary=imbalance_summary(imbalances_by_tf.get("1h", []), price),
        patterns=patterns_by_tf.get("1h", []),
        patterns_by_tf=patterns_by_tf,
        pattern_outlook_by_tf=pattern_outlook_by_tf,
    )

    deep = build_deep_analysis(
        partial,
        klines_1h,
        klines_4h,
        funding_history=funding_hist,
        oi_history=oi_hist,
        btc_change_24h=btc_chg,
    )

    if deep.divergences:
        signals.append(deep.divergences[0])
    signals.insert(3, f"Режим: {deep.market_regime} · Риск {deep.risk_label} ({deep.risk_score}/100)")

    partial.deep = deep

    try:
        from tis.core.data_cache import get_cached
        from tis.features.news_provider import build_query, fetch_news, sentiment_counts

        news_items = get_cached(
            f"news:{m}:{pair.upper()}",
            lambda: fetch_news(build_query(pair, m), 60, max_retries=1),
            ttl=300,
        )
        partial.news = sentiment_counts(news_items)
    except Exception:
        partial.news = None

    # Инсайдерский / «умные деньги» фактор: только для акций (US — SEC Form 4,
    # РФ — доли держателей). Кэш 6ч: SEC EDGAR медленный, данные меняются редко.
    partial.insider = None
    if m == "stock":
        try:
            from tis.core.data_cache import get_cached as _gc
            from tis.features.insider_provider import insider_signal

            partial.insider = _gc(
                f"insider:{pair.upper()}",
                lambda: insider_signal(pair, m),
                ttl=21600,
            )
        except Exception:
            partial.insider = None

    partial.accuracy = build_accuracy_metrics(partial, klines_4h)
    if partial.accuracy:
        signals.insert(
            4,
            f"Согласованность сигналов: {partial.accuracy.overall_pct}/100 · класс {partial.accuracy.confidence_grade}",
        )
    return partial
