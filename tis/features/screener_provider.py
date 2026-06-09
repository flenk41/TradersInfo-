"""Скринер: лёгкий расчёт сигналов по всей вселенной каталога.

В отличие от полного analyze_pair (дорогой, много ТФ), здесь по каждому
инструменту тянем ОДИН таймфрейм свечей и считаем быстрые индикаторы:
тренд (EMA20/50), RSI(14), изменение %, волатильность (ATR%). Этого хватает,
чтобы отфильтровать идеи; клик по строке открывает уже полный анализ.

Переиспользует индикаторы из analyzer.py и единый слой данных market_data.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from tis.analysis.accuracy_estimator import _quick_backtest_4h
from tis.analysis.analyzer import _atr, _ema, _rsi
from tis.data.instruments_catalog import CRYPTO_LIST, FOREX_LIST, STOCKS_RU, STOCKS_US
from tis.data.market_data import fetch_klines

_TF_LIMIT = {"1h": 120, "4h": 120, "1d": 160}
_MAX_WORKERS = 10  # лёгкие одиночные запросы свечей → можно много параллельных


def _universe(market: str, region: str):
    if market == "crypto":
        return CRYPTO_LIST
    if market == "forex":
        return FOREX_LIST
    if market == "stock":
        if region == "us":
            return STOCKS_US
        if region == "ru":
            return STOCKS_RU
        return STOCKS_RU + STOCKS_US
    return []


def _trend(price: float, ema20: float, ema50: float) -> str:
    if price > ema20 > ema50:
        return "bull"
    if price < ema20 < ema50:
        return "bear"
    return "flat"


def _signal(trend: str, rsi: float) -> str:
    """Короткий торговый ярлык по комбинации тренда и RSI."""
    if trend == "bull":
        if rsi < 40:
            return "bull_pullback"   # бычий тренд + откат — интересно для лонга
        if rsi > 72:
            return "overbought"
        return "uptrend"
    if trend == "bear":
        if rsi > 60:
            return "bear_pullback"
        if rsi < 28:
            return "oversold"
        return "downtrend"
    return "flat"


def _full_score(inst, df, trend: str, rsi: float, change_pct: float):
    """Балл согласованности.

    Если полный анализ инструмента УЖЕ лежит в кэше (его открывали в «Обзоре»),
    берём оттуда точное значение — совпадает с Обзором. Иначе считаем лёгкий
    прокси `_consistency` по одному ТФ. Скринер НЕ запускает полный analyze_pair
    сам (это было главным тормозом — ~5с на инструмент по всей вселенной).
    """
    try:
        from tis.core.data_cache import peek

        key = f"analyze:{inst.market or 'auto'}:{inst.id.upper()}"
        a = peek(key)
        if a is not None and getattr(a, "accuracy", None):
            return round(float(a.accuracy.overall_pct), 1)
    except Exception:
        pass
    return _consistency(df, trend, rsi, change_pct)


def _consistency(df, trend: str, rsi: float, change_pct: float) -> int:
    """Лёгкий балл согласованности (0–100) — ФОЛБЭК для скринера.

    Упрощённый прокси полного accuracy_estimator (тот требует мульти-ТФ).
    Считаем по одному ТФ: насколько простое правило EMA20/50+RSI исторически
    «попадало» (бэктест) и согласны ли тренд, RSI и импульс по направлению.
    """
    bt_rate, _bt_n = _quick_backtest_4h(df)  # 50.0 если данных мало
    if trend == "bull":
        d = "long"
    elif trend == "bear":
        d = "short"
    else:
        d = "neutral"
    if d == "neutral":
        align = 45.0  # флэт — направленные сигналы ненадёжны
    else:
        agree = 0
        if ("long" if rsi >= 50 else "short") == d:
            agree += 1
        if ("long" if change_pct >= 0 else "short") == d:
            agree += 1
        align = 40.0 + (agree / 2) * 45.0  # 40 / 62.5 / 85
    overall = round(bt_rate * 0.45 + align * 0.55)
    return int(max(35, min(92, overall)))


def _row(inst, tf: str):
    try:
        df = fetch_klines(inst.id, interval=tf, limit=_TF_LIMIT.get(tf, 120), market=inst.market)
    except Exception:
        return None
    if df is None or len(df) < 55:
        return None
    close = df["close"].astype(float)
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else price
    if price <= 0 or prev <= 0:
        return None
    try:
        ema20 = float(_ema(close, 20).iloc[-1])
        ema50 = float(_ema(close, 50).iloc[-1])
        rsi = round(_rsi(close), 1)
        atr_pct = round(_atr(df) / price * 100, 2)
    except Exception:
        return None
    trend = _trend(price, ema20, ema50)
    change_pct = round((price - prev) / prev * 100, 2)
    return {
        "id": inst.id,
        "name": inst.name,
        "subtitle": inst.subtitle or inst.id,
        "icon_url": inst.icon_url,
        "region": inst.region,
        "market": inst.market,
        "price": round(price, 6),
        "change_pct": change_pct,
        "rsi": rsi,
        "trend": trend,
        "atr_pct": atr_pct,
        "signal": _signal(trend, rsi),
        "score": _full_score(inst, df, trend, rsi, change_pct),
    }


def screen_market(market: str, region: str = "all", tf: str = "1d") -> dict:
    if tf not in _TF_LIMIT:
        tf = "1d"
    universe = _universe(market, region)
    rows = []
    # Каждый _row теперь делает лишь ОДИН лёгкий запрос свечей (полный анализ из
    # горячего пути убран) — нагрузка I/O-bound, поэтому поднимаем параллельность.
    # Результат скринера кэшируется на 5 мин (web_app), так что всплески редки.
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        for r in pool.map(lambda i: _row(i, tf), universe):
            if r is not None:
                rows.append(r)
    rows.sort(key=lambda r: r["change_pct"], reverse=True)
    return {"items": rows, "count": len(rows), "tf": tf}
