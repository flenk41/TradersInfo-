# SPDX-License-Identifier: AGPL-3.0-or-later
"""Публичные рыночные данные Bybit V5 (read-only, без API-ключа).

Используются ТОЛЬКО публичные эндпоинты `/v5/market/...` — ключ/подпись не нужны,
приватные операции (баланс/позиции/торговля) здесь сознательно не реализованы
(operator-safety: read-only). Формат возврата совпадает с `data_fetcher` (Binance),
чтобы Bybit подключался как альтернативный источник без правок анализа.

Зачем: Binance в РФ часто режется DPI; Bybit обычно доступен и отдаёт спот-свечи,
фандинг и открытый интерес — крипта работает полноценно без VPN.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests


class BybitDataError(Exception):
    pass


_TIMEOUT = 30
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.6
_session = requests.Session()

# Зеркала публичного API Bybit (bytick — официальное альтернативное доменное имя).
_MIRRORS = ["https://api.bybit.com", "https://api.bytick.com"]

# Binance-интервал -> Bybit-интервал (минуты числом, день/неделя буквой).
_INTERVAL = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
    "1d": "D", "1w": "W", "1M": "M",
}


def _get(path: str, params: dict[str, Any]) -> dict:
    """GET к публичному API Bybit с ретраями и перебором зеркал."""
    last_exc: Exception | None = None
    for host in _MIRRORS:
        full = f"{host}{path}"
        for attempt in range(_MAX_RETRIES):
            try:
                resp = _session.get(full, params=params, timeout=_TIMEOUT)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_BASE * (2 ** attempt))
                    continue
                break  # к следующему зеркалу
            if resp.status_code in (403, 429) and attempt < _MAX_RETRIES - 1:
                time.sleep(_BACKOFF_BASE * (2 ** attempt))
                continue
            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                last_exc = exc
                break
            data = resp.json()
            if data.get("retCode") != 0:
                raise BybitDataError(f"Bybit: {data.get('retMsg', 'ошибка')}")
            return data.get("result") or {}
    raise BybitDataError(
        f"Bybit недоступен через {', '.join(_MIRRORS)}. Последняя ошибка: {last_exc}"
    )


def _bybit_interval(interval: str) -> str:
    return _INTERVAL.get(interval, "60")


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    """Спот-свечи. Bybit отдаёт от новых к старым — переворачиваем в хронологию."""
    res = _get(
        "/v5/market/kline",
        {"category": "spot", "symbol": symbol, "interval": _bybit_interval(interval), "limit": min(limit, 1000)},
    )
    rows = res.get("list") or []
    if not rows:
        raise BybitDataError(f"Bybit: нет свечей для {symbol}")
    # [start_ms, open, high, low, close, volume, turnover]
    rows = list(reversed(rows))
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume", "quote_volume"])
    for col in ("open", "high", "low", "close", "volume", "quote_volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_datetime(pd.to_numeric(df["open_time"], errors="coerce"), unit="ms")
    return df


def _spot_ticker(symbol: str) -> dict:
    res = _get("/v5/market/tickers", {"category": "spot", "symbol": symbol})
    lst = res.get("list") or []
    if not lst:
        raise BybitDataError(f"Bybit: тикер {symbol} не найден")
    return lst[0]


def fetch_ticker_24h(symbol: str) -> dict[str, Any]:
    """24ч-тикер в формате ключей Binance (lastPrice/priceChangePercent/...)."""
    t = _spot_ticker(symbol)
    last = float(t.get("lastPrice", 0))
    pcnt = float(t.get("price24hPcnt", 0)) * 100  # Bybit отдаёт долей (0.0123)
    return {
        "lastPrice": last,
        "priceChangePercent": round(pcnt, 4),
        "highPrice": float(t.get("highPrice24h", 0) or 0),
        "lowPrice": float(t.get("lowPrice24h", 0) or 0),
        "quoteVolume": float(t.get("turnover24h", 0) or 0),
        "volume": float(t.get("volume24h", 0) or 0),
    }


def _linear_ticker(symbol: str) -> dict | None:
    try:
        res = _get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
        lst = res.get("list") or []
        return lst[0] if lst else None
    except BybitDataError:
        return None


def fetch_funding_rate(symbol: str) -> dict[str, Any] | None:
    t = _linear_ticker(symbol)
    if not t or t.get("fundingRate") in (None, ""):
        return None
    try:
        rate = float(t["fundingRate"])
        nxt = t.get("nextFundingTime")
        return {
            "rate": rate,
            "rate_percent": rate * 100,
            "next_funding_time": pd.to_datetime(int(nxt), unit="ms") if nxt else pd.Timestamp.utcnow(),
            "mark_price": float(t.get("markPrice", 0) or 0),
            "index_price": float(t.get("indexPrice", 0) or 0),
        }
    except (ValueError, TypeError):
        return None


def fetch_open_interest(symbol: str) -> float | None:
    """Открытый интерес перпетуала (в базовой монете), как у Binance."""
    t = _linear_ticker(symbol)
    if not t:
        return None
    try:
        oi = t.get("openInterest")
        return float(oi) if oi not in (None, "") else None
    except (ValueError, TypeError):
        return None


def fetch_open_interest_history(symbol: str, period: str = "1h", limit: int = 48) -> list[dict]:
    try:
        res = _get(
            "/v5/market/open-interest",
            {"category": "linear", "symbol": symbol, "intervalTime": period, "limit": min(limit, 200)},
        )
        rows = res.get("list") or []
        out = []
        for row in reversed(rows):  # новые → старые, переворачиваем
            try:
                out.append({
                    "time": int(row["timestamp"]) // 1000,
                    "sumOpenInterest": float(row["openInterest"]),
                    "sumOpenInterestValue": 0.0,
                })
            except (ValueError, TypeError, KeyError):
                continue
        return out
    except BybitDataError:
        return []


def fetch_funding_history(symbol: str, limit: int = 90) -> list[dict]:
    try:
        res = _get(
            "/v5/market/funding/history",
            {"category": "linear", "symbol": symbol, "limit": min(limit, 200)},
        )
        rows = res.get("list") or []
        points = []
        for row in rows:
            try:
                points.append({
                    "time": int(row["fundingRateTimestamp"]) // 1000,
                    "value": round(float(row["fundingRate"]) * 100, 4),
                })
            except (ValueError, TypeError, KeyError):
                continue
        points.sort(key=lambda x: x["time"])
        return points
    except BybitDataError:
        return []


def fetch_btc_change_24h() -> float | None:
    try:
        return fetch_ticker_24h("BTCUSDT")["priceChangePercent"]
    except BybitDataError:
        return None


def validate_symbol(symbol: str) -> bool:
    try:
        _spot_ticker(symbol)
        return True
    except BybitDataError:
        return False


def fetch_long_short_ratio(symbol: str, period: str = "1h") -> dict | None:
    """Доля аккаунтов в лонге/шорте по перпетуалу (сентимент толпы).

    Деривативный эндпоинт — в части регионов отдаёт 403; тогда возвращаем None.
    """
    try:
        res = _get(
            "/v5/market/account-ratio",
            {"category": "linear", "symbol": symbol, "period": period, "limit": 1},
        )
        lst = res.get("list") or []
        if not lst:
            return None
        row = lst[0]
        buy = float(row.get("buyRatio") or 0)
        sell = float(row.get("sellRatio") or 0)
        if buy <= 0 and sell <= 0:
            return None
        return {
            "long_pct": round(buy * 100, 1),
            "short_pct": round(sell * 100, 1),
            "period": period,
        }
    except (BybitDataError, ValueError, TypeError):
        return None


def fetch_orderbook_imbalance(symbol: str, depth: int = 50) -> dict | None:
    """Дисбаланс стакана (спот): объём бидов vs асков у текущей цены.

    >50% bid — давление покупателей. Спот-стакан публичный, работает без ключа.
    """
    try:
        res = _get("/v5/market/orderbook", {"category": "spot", "symbol": symbol, "limit": min(depth, 200)})
        bids = res.get("b") or []
        asks = res.get("a") or []
        if not bids or not asks:
            return None
        bid_vol = sum(float(p[1]) for p in bids)
        ask_vol = sum(float(p[1]) for p in asks)
        total = bid_vol + ask_vol
        if total <= 0:
            return None
        bid_pct = round(bid_vol / total * 100, 1)
        return {
            "bid_pct": bid_pct,
            "ask_pct": round(100 - bid_pct, 1),
            "best_bid": float(bids[0][0]),
            "best_ask": float(asks[0][0]),
            "levels": len(bids) + len(asks),
        }
    except (BybitDataError, ValueError, TypeError, IndexError):
        return None
