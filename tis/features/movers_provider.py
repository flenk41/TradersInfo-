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

from tis.data.instruments_catalog import CRYPTO_LIST, FOREX_LIST, STOCKS_RU, STOCKS_US
from tis.data.market_data import fetch_klines

_RANGE_DAYS = {"day": 1, "month": 30, "year": 365}


def _sparkline(closes, n: int = 24) -> list[float]:
    """Сжимает ряд цен до n точек для мини-графика на карточке (фронт нормирует)."""
    vals = [float(c) for c in closes if c is not None]
    if not vals:
        return []
    if len(vals) <= n:
        return [round(v, 6) for v in vals]
    step = len(vals) / n
    return [round(vals[min(len(vals) - 1, int(i * step))], 6) for i in range(n)]


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
    row = _row(inst, last, (last - old) / old * 100)
    # Ряд для спарклайна — из уже загруженных свечей (без доп. запросов).
    row["spark"] = _sparkline(closes[idx:])
    return row


def _crypto_day() -> list[dict]:
    """Быстрый путь: один запрос всех 24ч-тикеров Binance."""
    from tis.data.data_fetcher import fetch_all_tickers_24h

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


def strip_quotes(market: str, ids: list[str]) -> dict:
    """Цена + изменение + спарклайн для небольшого набора инструментов (полоса сверху).

    Вызывается только для видимых/кураторских карточек (caller ограничивает кол-во).
    Крипта — 1h-ряд (изм. за ~24ч), акции/форекс — дневной ряд (изм. за день).
    Использует market_data.fetch_klines (с Yahoo-фолбэком для крипты).
    """
    interval = "1h" if market == "crypto" else "1d"
    limit = 48 if market == "crypto" else 32
    look = 24 if market == "crypto" else 1

    def _load(iid: str):
        try:
            df = fetch_klines(iid, interval=interval, limit=limit, market=market)
            closes = [float(c) for c in df["close"].tolist() if c is not None]
            if len(closes) < 2:
                return iid, None
            last = closes[-1]
            prev = closes[max(0, len(closes) - 1 - look)]
            change = (last - prev) / prev * 100 if prev else 0.0
            return iid, {"price": round(last, 6), "change_pct": round(change, 2), "spark": _sparkline(closes)}
        except Exception:
            return iid, None

    out: dict[str, dict] = {}
    if ids:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for iid, q in pool.map(_load, ids):
                if q:
                    out[iid] = q
    return out


def _attach_crypto_sparklines(rows: list[dict]) -> None:
    """Догружает 1h-ряд для спарклайна по уникальным id (для крипто-дня)."""
    uniq = {r["id"]: r for r in rows}

    def _load(rid: str):
        try:
            df = fetch_klines(rid, interval="1h", limit=48, market="crypto")
            return rid, _sparkline(df["close"].tolist())
        except Exception:
            return rid, []

    spark_by_id: dict[str, list] = {}
    if uniq:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for rid, spark in pool.map(_load, list(uniq.keys())):
                spark_by_id[rid] = spark
    for r in rows:
        r["spark"] = spark_by_id.get(r["id"], [])


def fetch_movers(market: str, range_key: str = "day", region: str = "all", top: int = 12) -> dict:
    days = _RANGE_DAYS.get(range_key, 1)

    rows: list[dict] = []
    fast_crypto = market == "crypto" and range_key == "day"
    if fast_crypto:
        # Быстрый путь — один bulk-тикер Binance. Если Binance недоступен (451/обрыв),
        # падаем на per-инструмент klines (там есть Yahoo-фолбэк), чтобы экран жил.
        try:
            rows = _crypto_day()
        except Exception:
            rows = []
    if not rows:
        universe = _universe(market, region)
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

    # Крипто-день идёт быстрым путём (24ч-тикер, без рядов) — догружаем спарклайны
    # только для отображаемых карточек (топ рост/падение), чтобы не тянуть всё.
    if market == "crypto" and range_key == "day":
        _attach_crypto_sparklines(gainers + losers)
    return {
        "items": rows,
        "gainers": gainers,
        "losers": losers,
        "count": len(rows),
        "top_gainer": gainers[0] if gainers else None,
        "top_loser": losers[0] if losers else None,
    }
