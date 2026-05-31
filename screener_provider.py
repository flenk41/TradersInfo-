"""Скринер: лёгкий расчёт сигналов по всей вселенной каталога.

В отличие от полного analyze_pair (дорогой, много ТФ), здесь по каждому
инструменту тянем ОДИН таймфрейм свечей и считаем быстрые индикаторы:
тренд (EMA20/50), RSI(14), изменение %, волатильность (ATR%). Этого хватает,
чтобы отфильтровать идеи; клик по строке открывает уже полный анализ.

Переиспользует индикаторы из analyzer.py и единый слой данных market_data.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from analyzer import _atr, _ema, _rsi
from instruments_catalog import CRYPTO_LIST, FOREX_LIST, STOCKS_RU, STOCKS_US
from market_data import fetch_klines

_TF_LIMIT = {"1h": 120, "4h": 120, "1d": 160}


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
    return {
        "id": inst.id,
        "name": inst.name,
        "subtitle": inst.subtitle or inst.id,
        "icon_url": inst.icon_url,
        "region": inst.region,
        "market": inst.market,
        "price": round(price, 6),
        "change_pct": round((price - prev) / prev * 100, 2),
        "rsi": rsi,
        "trend": trend,
        "atr_pct": atr_pct,
        "signal": _signal(trend, rsi),
    }


def screen_market(market: str, region: str = "all", tf: str = "1d") -> dict:
    if tf not in _TF_LIMIT:
        tf = "1d"
    universe = _universe(market, region)
    rows = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for r in pool.map(lambda i: _row(i, tf), universe):
            if r is not None:
                rows.append(r)
    rows.sort(key=lambda r: r["change_pct"], reverse=True)
    return {"items": rows, "count": len(rows), "tf": tf}
