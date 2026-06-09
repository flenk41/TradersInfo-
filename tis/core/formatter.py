"""Форматирование отчёта анализа."""

from __future__ import annotations

from tis.analysis.analyzer import MarketAnalysis


def _line(char: str = "─", width: int = 50) -> str:
    return char * width


def format_price(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def format_volume(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}"


def format_analysis(analysis: MarketAnalysis) -> str:
    lines: list[str] = []
    change_sign = "+" if analysis.change_24h_pct >= 0 else ""

    lines.append(_line("═"))
    lines.append(f"  📊 АНАЛИЗ: {analysis.symbol}")
    lines.append(_line("═"))
    lines.append("")
    lines.append("💰 ЦЕНА")
    lines.append(f"   Текущая:     ${format_price(analysis.price)}")
    lines.append(f"   24ч:         {change_sign}{analysis.change_24h_pct:.2f}%")
    lines.append(f"   Макс 24ч:    ${format_price(analysis.high_24h)}")
    lines.append(f"   Мин 24ч:     ${format_price(analysis.low_24h)}")
    lines.append(f"   Объём 24ч:   ${format_volume(analysis.volume_24h)}")
    lines.append("")
    lines.append(_line())
    lines.append("📈 ТРЕНД")
    lines.append(f"   Общий:       {analysis.overall_trend}")
    lines.append(f"   {analysis.trend_summary}")
    if analysis.bias:
        lines.append(f"   HTF Bias:    {analysis.bias.direction.upper()} — {analysis.bias.summary}")
        lines.append(f"   Правило:     {analysis.bias.trade_rule}")
    lines.append("")
    for tf in analysis.timeframes:
        lines.append(f"   [{tf.timeframe.upper():>3}] {tf.trend} ({tf.trend_strength})")
        lines.append(f"         Структура: {tf.market_structure} | ADX {tf.adx} ({tf.adx_label})")
        sma = f"${format_price(tf.sma200)}" if tf.sma200 else "—"
        lines.append(
            f"         RSI {tf.rsi} | MACD {tf.macd_trend} | {tf.macd_cross}"
        )
        lines.append(f"         {tf.volume_note}")
    lines.append("")
    lines.append(_line())

    if analysis.trade:
        t = analysis.trade
        lines.append("🎯 РЕКОМЕНДАЦИЯ ПО ВХОДУ")
        lines.append(f"   Лучшее:      {t.best_action}")
        lines.append(f"   ЛОНГ:        {t.long_verdict} ({t.long_score}/100)")
        lines.append(f"   ШОРТ:        {t.short_verdict} ({t.short_score}/100)")
        lines.append(f"   Уверенность: {t.confidence}")
        lines.append(f"   {t.entry_price_hint}")
        lines.append(f"   {t.stop_loss_hint}")
        lines.append(f"   {t.take_profit_hint}")
        if t.warnings:
            for w in t.warnings:
                lines.append(f"   ⚠ {w}")
        lines.append("")
        lines.append(_line())

    if analysis.accuracy:
        acc = analysis.accuracy
        lines.append("📊 СОГЛАСОВАННОСТЬ СИГНАЛОВ")
        lines.append(f"   Балл:        {acc.overall_pct}/100 (класс {acc.confidence_grade})")
        lines.append(f"   Надёжность:  {acc.reliability_label}")
        lines.append(f"   ТФ согласие: {acc.timeframe_alignment_pct}%")
        lines.append(f"   Бэктест 4H:  {acc.backtest_hit_rate}% ({acc.backtest_samples} сэмплов)")
        lines.append(f"   {acc.explanation}")
        lines.append("")
        lines.append(_line())

    if analysis.fibonacci:
        fib = analysis.fibonacci
        lines.append("📐 ФИБОНАЧЧИ (4H)")
        lines.append(f"   Свинг:       ${format_price(fib.swing_low)} — ${format_price(fib.swing_high)}")
        lines.append(f"   Направление: {fib.direction}")
        lines.append(f"   Зона:        {fib.current_zone}")
        if fib.in_golden_zone:
            lines.append("   ★ Золотая зона 38.2%–61.8%")
        lines.append(f"   {fib.entry_hint}")
        lines.append(f"   Лонг зона:   {fib.optimal_long_zone}")
        lines.append(f"   Шорт зона:   {fib.optimal_short_zone}")
        lines.append("   Уровни:")
        for lvl in fib.levels:
            marker = " ◀" if abs(lvl.price - analysis.price) / analysis.price < 0.005 else ""
            lines.append(f"      {lvl.label:>6}  ${format_price(lvl.price)}{marker}")
        lines.append("")
        lines.append(_line())

    if analysis.volatility:
        v = analysis.volatility
        lines.append("⚡ ВОЛАТИЛЬНОСТЬ")
        lines.append(f"   Уровень:     {v.level}")
        lines.append(f"   {v.description}")
        lines.append(f"   ATR(14):     ${format_price(v.atr_14)} ({v.atr_percent}%)")
        lines.append(f"   Дневная σ:   {v.daily_volatility_pct}%")
        lines.append(f"   Диапазон 24ч:{v.range_24h_pct}%")
        lines.append("")
        lines.append(_line())

    if analysis.funding:
        f = analysis.funding
        sign = "+" if f.rate_percent >= 0 else ""
        lines.append("💸 ФАНДИНГ (Futures)")
        lines.append(f"   Ставка:      {sign}{f.rate_percent:.4f}%")
        lines.append(f"   Качество:    {f.quality or '—'}")
        lines.append(f"   ЛОНГ:        {f.long_action or '—'}")
        if f.long_reason:
            lines.append(f"               {f.long_reason}")
        lines.append(f"   ШОРТ:        {f.short_action or '—'}")
        if f.short_reason:
            lines.append(f"               {f.short_reason}")
        if f.summary:
            lines.append(f"   Итог:        {f.summary}")
        lines.append(f"   Настроение:  {f.sentiment}")
        lines.append(f"   Mark Price:  ${format_price(f.mark_price)}")
        lines.append(f"   Index Price: ${format_price(f.index_price)}")
        if f.open_interest is not None:
            lines.append(f"   Open Int.:   {format_volume(f.open_interest)}")
        lines.append(f"   След. фанд.: {f.next_funding_time}")
        lines.append("")
        lines.append(_line())
    else:
        lines.append("💸 ФАНДИНГ: недоступен (нет фьючерсной пары на Binance)")
        lines.append("")
        lines.append(_line())

    if analysis.support_levels or analysis.resistance_levels:
        lines.append("🎯 УРОВНИ")
        if analysis.resistance_levels:
            levels = " | ".join(f"${format_price(l)}" for l in analysis.resistance_levels)
            lines.append(f"   Сопротивление: {levels}")
        if analysis.support_levels:
            levels = " | ".join(f"${format_price(l)}" for l in analysis.support_levels)
            lines.append(f"   Поддержка:     {levels}")
        lines.append("")
        lines.append(_line())

    if analysis.signals:
        lines.append("🔔 СИГНАЛЫ")
        for signal in analysis.signals:
            lines.append(f"   • {signal}")
        lines.append("")

    if analysis.deep:
        d = analysis.deep
        lines.append(_line())
        lines.append("🔬 ГЛУБОКИЙ АНАЛИЗ")
        lines.append(f"   {d.executive_summary}")
        lines.append(f"   Режим: {d.market_regime} — {d.regime_description}")
        lines.append(f"   Риск: {d.risk_label} ({d.risk_score}/100)")
        lines.append(f"   Схождение: лонг {d.confluence_long}% · шорт {d.confluence_short}%")
        if d.btc_context:
            lines.append(f"   BTC: {d.btc_context}")
        lines.append(f"   {d.funding_trend}")
        lines.append(f"   {d.oi_trend}")
        for div in d.divergences:
            lines.append(f"   • {div}")
        for sc in d.scenarios:
            lines.append(f"   [{sc.title} {sc.probability}] {sc.trigger} → {sc.target}")
        lines.append("")

    lines.append(_line("═"))
    lines.append("  ⚠️  Не является финансовой рекомендацией")
    lines.append(_line("═"))

    return "\n".join(lines)


def format_position(p) -> str:
    lines: list[str] = []
    lines.append(_line("═"))
    lines.append(f"  💼 ВАША ПОЗИЦИЯ: {p.side_label}")
    lines.append(_line("═"))
    lines.append("")
    lines.append(f"   Вход:        ${format_price(p.entry_price)}")
    lines.append(f"   Текущая:     ${format_price(p.current_price)}  →  {p.status}")
    lines.append(f"   Маржа:       {p.margin_usdt:.2f} USDT")
    lines.append(f"   Плечо:       x{p.leverage}")
    lines.append(f"   Объём:       {p.position_notional_usdt:.2f} USDT ({p.quantity} монет)")
    lines.append("")
    lines.append(_line())
    lines.append("🛑 СТОП-ЛОСС")
    lines.append(f"   Цена:        ${format_price(p.stop_loss)} (−{p.sl_distance_pct}% от входа)")
    lines.append(f"   {p.stop_reason}")
    lines.append(f"   Убыток:      {p.pnl_sl_usdt:.2f} USDT ({p.pnl_sl_pct:.2f}% от маржи)")
    lines.append("")
    lines.append("🎯 ТЕЙК-ПРОФИТ")
    lines.append(f"   Цена:        ${format_price(p.take_profit)} (+{p.tp_distance_pct}% от входа)")
    lines.append(f"   {p.tp_reason}")
    lines.append(f"   Прибыль:     +{p.pnl_tp_usdt:.2f} USDT (+{p.pnl_tp_pct:.2f}% от маржи)")
    lines.append("")
    lines.append(f"   R:R         1:{p.risk_reward} (мин. 1:2.5)")
    if p.take_profit_2:
        lines.append(f"   TP2:         ${format_price(p.take_profit_2)}")
    if not p.aligned_with_market:
        lines.append("   ⚠ Позиция ПРОТИВ старшего тренда")
    lines.append(f"   {p.advice}")
    lines.append("")
    lines.append(_line("═"))
    return "\n".join(lines)
