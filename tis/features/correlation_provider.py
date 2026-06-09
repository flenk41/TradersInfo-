"""Корреляции: какие инструменты движутся вместе с выбранным, а какие — против.

Считаем корреляцию Пирсона по дневным доходностям (~120 дней) между базовым
инструментом и вселенной его рынка. Матрица доходностей по рынку кэшируется
(дорого строить), поэтому корреляции для любого базового актива дешёвы.
Полезно для диверсификации и подтверждения движения.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from tis.data.instruments_catalog import CRYPTO_LIST, FOREX_LIST, STOCKS_RU, STOCKS_US, get_instrument
from tis.data.market_data import fetch_klines

_DAYS = 120
_MIN_OVERLAP = 30


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


def _returns(pair: str, market: str | None):
    df = fetch_klines(pair, interval="1d", limit=_DAYS, market=market)
    s = df.set_index(df["open_time"].dt.normalize())["close"].astype(float)
    s = s[~s.index.duplicated(keep="last")]
    return s.pct_change().dropna()


def _safe_returns(pair: str, market: str | None):
    try:
        r = _returns(pair, market)
        return r if len(r) > 40 else None
    except Exception:
        return None


def returns_matrix(market: str, region: str) -> pd.DataFrame:
    uni = _universe(market, region)
    cols: dict[str, pd.Series] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for inst, r in zip(uni, pool.map(lambda i: _safe_returns(i.id, i.market), uni)):
            if r is not None:
                cols[inst.id] = r
    return pd.DataFrame(cols)


def _item(pair_id: str, market: str, corr: float) -> dict:
    inst = get_instrument(pair_id, market)
    return {
        "id": pair_id,
        "name": inst.name if inst else pair_id,
        "subtitle": (inst.subtitle if inst else pair_id) or pair_id,
        "icon_url": inst.icon_url if inst else "",
        "region": inst.region if inst else "",
        "market": inst.market if inst else market,
        "corr": round(float(corr), 2),
    }


def correlations(pair: str, market: str, region: str = "all", top: int = 6) -> dict:
    base_id = pair.strip().upper()
    matrix = returns_matrix(market, region)
    if base_id not in matrix.columns:
        base = _safe_returns(pair, market)
        if base is None:
            return {"positive": [], "negative": [], "count": 0}
        matrix = matrix.copy()
        matrix[base_id] = base
    if matrix.shape[1] < 2:
        return {"positive": [], "negative": [], "count": 0}

    corr = matrix.corr(min_periods=_MIN_OVERLAP)[base_id].drop(labels=[base_id], errors="ignore").dropna()
    if corr.empty:
        return {"positive": [], "negative": [], "count": 0}

    pos = corr.sort_values(ascending=False)
    neg = corr.sort_values()
    positive = [_item(idx, market, v) for idx, v in pos.head(top).items() if v > 0.1]
    negative = [_item(idx, market, v) for idx, v in neg.head(top).items() if v < -0.05]
    return {"positive": positive, "negative": negative, "count": int(corr.shape[0])}
