"""Экран движений рынка: топ-растущие и топ-падающие инструменты каталога.

Источник изменения цены:
- крипто, день — единый 24ч-тикер Binance (1 запрос на все символы);
- остальное — дневные свечи через market_data.fetch_klines (крипто→Binance,
  RU-акции→MOEX, US-акции/форекс→Yahoo), сравнивается цена N дней назад и последняя.

Запросов может быть много (по инструменту), поэтому вызывается в пуле потоков,
а результат кэшируется в эндпоинте.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from instruments_catalog import CRYPTO_LIST, FOREX_LIST, STOCKS_RU, STOCKS_US
from market_data import fetch_klines

_RANGE_DAYS = {"day": 1, "month": 30, "year": 365}


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


def _row(inst, price: float, change_pct: float) -> dict:
    return {
        "id": inst.id,
        "name": inst.name,
        "subtitle": inst.subtitle or inst.id,
        "icon_url": inst.icon_url,
        "region": inst.region,
        "market": inst.market,
        "price": round(float(price), 6),
        "change_pct": round(float(change_pct), 2),
    }


def _change_from_klines(inst, days: int) -> dict | None:
    limit = min(max(days + 3, 4), 400)
    df = fetch_klines(inst.id, interval="1d", limit=limit, market=inst.market)
    closes = df["close"].tolist()
    if len(closes) < 2:
        return None
    last = float(closes[-1])
    idx = max(0, len(closes) - 1 - days)
    old = float(closes[idx])
    if old <= 0:
        return None
    return _row(inst, last, (last - old) / old * 100)


def _crypto_day() -> list[dict]:
    """Быстрый путь: один запрос всех 24ч-тикеров Binance."""
    from data_fetcher import fetch_all_tickers_24h

    tickers = {t.get("symbol"): t for t in fetch_all_tickers_24h()}
    rows = []
    for inst in CRYPTO_LIST:
        sym = inst.id.replace("/", "")
        t = tickers.get(sym)
        if not t:
            continue
        try:
            rows.append(_row(inst, float(t["lastPrice"]), float(t["priceChangePercent"])))
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def fetch_movers(market: str, range_key: str = "day", region: str = "all", top: int = 12) -> dict:
    days = _RANGE_DAYS.get(range_key, 1)

    if market == "crypto" and range_key == "day":
        rows = _crypto_day()
    else:
        universe = _universe(market, region)
        rows = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_change_from_klines, i, days): i for i in universe}
            for fut in as_completed(futures):
                try:
                    r = fut.result()
                    if r is not None:
                        rows.append(r)
                except Exception:
                    pass

    rows.sort(key=lambda r: r["change_pct"], reverse=True)
    gainers = rows[:top]
    losers = sorted(rows, key=lambda r: r["change_pct"])[:top]
    return {
        "items": rows,
        "gainers": gainers,
        "losers": losers,
        "count": len(rows),
        "top_gainer": gainers[0] if gainers else None,
        "top_loser": losers[0] if losers else None,
    }
