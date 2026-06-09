"""Полная вселенная инструментов для поиска.

Каталог (instruments_catalog) — это кураторские «быстрые» списки для полос и
экрана движений. Здесь же — ПОЛНЫЕ списки для поиска: все спот-пары Binance и
все бумаги MOEX (живые запросы с кэшем). Для США/форекса берём расширенный
каталог (бесплатной базы «всех» тикеров мира не существует).
"""

from __future__ import annotations

from tis.data.instruments_catalog import (
    CRYPTO_LIST,
    FOREX_LIST,
    STOCKS_RU,
    STOCKS_US,
    _stock_icon_ru,
)

_CRYPTO_ICON = "https://assets.coincap.io/assets/icons/{}@2x.png"


def _inst_dict(i) -> dict:
    return {
        "id": i.id,
        "name": i.name,
        "subtitle": i.subtitle or i.id,
        "market": i.market,
        "region": i.region,
        "icon_url": i.icon_url,
    }


def _crypto_universe() -> list[dict]:
    from tis.data.data_fetcher import fetch_exchange_info

    info = fetch_exchange_info()
    out = []
    for s in info.get("symbols", []):
        if s.get("status") != "TRADING" or s.get("quoteAsset") != "USDT":
            continue
        base = s.get("baseAsset")
        if not base:
            continue
        out.append({
            "id": f"{base}/USDT",
            "name": base,
            "subtitle": base,
            "market": "crypto",
            "region": "",
            "icon_url": _CRYPTO_ICON.format(base.lower()),
        })
    out.sort(key=lambda r: r["id"])
    return out


def _ru_universe() -> list[dict]:
    # Большой ответ MOEX (~120 КБ): общая keep-alive сессия его обрывает,
    # поэтому делаем отдельный запрос с Connection: close и своими ретраями.
    import time

    import requests

    url = (
        "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/"
        "securities.json?iss.meta=off&securities.columns=SECID,SHORTNAME"
    )
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Connection": "close"}
    last_exc = None
    r = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=25)
            r.raise_for_status()
            break
        except requests.RequestException as exc:
            last_exc = exc
            r = None
            if attempt < 2:
                time.sleep(0.6 * (2 ** attempt))
    if r is None:
        raise last_exc or RuntimeError("MOEX: не удалось получить список бумаг")

    block = r.json().get("securities", {})
    cols = block.get("columns", [])
    rows = block.get("data", [])
    try:
        si, ni = cols.index("SECID"), cols.index("SHORTNAME")
    except ValueError:
        return []
    out = []
    for row in rows:
        secid = row[si]
        if not secid:
            continue
        out.append({
            "id": f"{secid}.ME",
            "name": row[ni] or secid,
            "subtitle": secid,
            "market": "stock",
            "region": "ru",
            "icon_url": _stock_icon_ru(secid),
        })
    out.sort(key=lambda r: r["name"])
    return out


def get_universe(market: str, region: str = "all") -> list[dict]:
    """Полный список инструментов рынка (с кэшем для живых источников)."""
    from tis.core.data_cache import get_cached

    if market == "crypto":
        try:
            return get_cached("uni:crypto", _crypto_universe, ttl=21600)
        except Exception:
            return [_inst_dict(i) for i in CRYPTO_LIST]
    if market == "forex":
        return [_inst_dict(i) for i in FOREX_LIST]
    if market == "stock":
        us = [_inst_dict(i) for i in STOCKS_US]
        if region == "us":
            return us
        try:
            ru = get_cached("uni:ru", _ru_universe, ttl=21600)
        except Exception:
            ru = [_inst_dict(i) for i in STOCKS_RU]
        if region == "ru":
            return ru
        return ru + us
    return []


def search_universe(market: str, region: str = "all", query: str = "", limit: int = 600) -> list[dict]:
    items = get_universe(market, region)
    q = query.strip().lower()
    if q:
        items = [
            it for it in items
            if q in it["id"].lower() or q in it["name"].lower() or q in it["subtitle"].lower()
        ]
    return items[:limit]
