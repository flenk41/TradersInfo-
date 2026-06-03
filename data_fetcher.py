"""Получение рыночных данных с Binance."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests

from config import BINANCE_FUTURES_URL, BINANCE_SPOT_URL, DEFAULT_QUOTE


class BinanceDataError(Exception):
    pass


class RateLimitedError(BinanceDataError):
    """Биржа вернула 429/418 — слишком много запросов."""


class GeoBlockedError(BinanceDataError):
    """Биржа вернула 451 — доступ заблокирован для этого региона/IP."""


_TIMEOUT = 30
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.6  # сек; растёт экспоненциально: 0.6, 1.2, 2.4 ...
_session = requests.Session()

# Зеркала публичных данных Binance. Когда основной хост зарезан DPI/файрволом
# (типичная картина в РФ: обрыв TLS, WinError 10053), пробуем альтернативы.
# data-api.binance.vision — публичные данные без ключей, часто доступен где api.binance.com нет.
_SPOT_MIRRORS = [
    BINANCE_SPOT_URL,
    "https://api-gcp.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://data-api.binance.vision",
]
_FUTURES_MIRRORS = [
    BINANCE_FUTURES_URL,
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
]


def _mirrors_for(url: str) -> list[str]:
    """Список хостов-кандидатов для перебора при сетевом обрыве."""
    if url == BINANCE_FUTURES_URL:
        return _FUTURES_MIRRORS
    if url == BINANCE_SPOT_URL:
        return _SPOT_MIRRORS
    return [url]


def normalize_symbol(pair: str, quote: str = DEFAULT_QUOTE) -> str:
    """ETH/USDT, eth-usdt, ETHUSDT -> ETHUSDT."""
    cleaned = pair.strip().upper().replace("-", "").replace("_", "")
    if "/" in cleaned:
        base, q = cleaned.split("/", 1)
        return f"{base}{q}"
    if cleaned.endswith(quote):
        return cleaned
    return f"{cleaned}{quote}"


def _get(url: str, path: str, params: dict[str, Any] | None = None) -> Any:
    """GET к Binance с ретраями и перебором зеркал при сетевом обрыве.

    Сначала исчерпываем ретраи на основном хосте; если все попытки упали по сети
    (таймаут/обрыв TLS — типично при блокировке в РФ), переходим к следующему зеркалу.
    """
    hosts = _mirrors_for(url)
    last_exc: Exception | None = None
    network_fail = False

    for host in hosts:
        full = f"{host}{path}"
        for attempt in range(_MAX_RETRIES):
            try:
                response = _session.get(full, params=params, timeout=_TIMEOUT)
            except requests.RequestException as exc:
                # Сетевые сбои/таймауты — повторяем с backoff, затем пробуем след. зеркало.
                last_exc = exc
                network_fail = True
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_BASE * (2 ** attempt))
                    continue
                break  # к следующему хосту

            status = response.status_code

            if status == 451:
                raise GeoBlockedError(
                    "Доступ к Binance заблокирован для этого IP/региона (HTTP 451). "
                    "На облачном хостинге (Render и т.п.) используйте прокси или другой источник данных."
                )

            if status in (418, 429):
                # Слишком много запросов: уважаем Retry-After, иначе экспоненциальный backoff.
                if attempt < _MAX_RETRIES - 1:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else _BACKOFF_BASE * (2 ** attempt)
                    time.sleep(min(delay, 5.0))
                    continue
                raise RateLimitedError(
                    "Биржа ограничила частоту запросов (HTTP 429). Подождите и повторите."
                )

            if status >= 500:
                # Временная ошибка биржи — повторяем.
                last_exc = requests.HTTPError(f"HTTP {status}", response=response)
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_BASE * (2 ** attempt))
                    continue
                response.raise_for_status()

            response.raise_for_status()
            return response.json()

    if network_fail:
        raise BinanceDataError(
            "Сеть недоступна: не удалось подключиться к Binance ни через один из хостов "
            f"({', '.join(hosts)}). Похоже, провайдер блокирует Binance — используйте VPN/прокси. "
            f"Последняя ошибка: {last_exc}"
        ) from last_exc
    if last_exc:
        raise BinanceDataError(str(last_exc)) from last_exc
    raise BinanceDataError("Не удалось получить данные")


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    data = _get(
        BINANCE_SPOT_URL,
        "/api/v3/klines",
        {"symbol": symbol, "interval": interval, "limit": limit},
    )
    df = pd.DataFrame(
        data,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )
    numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df


def fetch_ticker_24h(symbol: str) -> dict[str, Any]:
    return _get(BINANCE_SPOT_URL, "/api/v3/ticker/24hr", {"symbol": symbol})


def fetch_all_tickers_24h() -> list[dict[str, Any]]:
    """Все 24ч-тикеры одним запросом (для экрана движений по крипте)."""
    data = _get(BINANCE_SPOT_URL, "/api/v3/ticker/24hr")
    return data if isinstance(data, list) else []


def fetch_exchange_info() -> dict[str, Any]:
    """Полный список торгуемых пар Binance (для поиска по всем монетам)."""
    return _get(BINANCE_SPOT_URL, "/api/v3/exchangeInfo")


def fetch_funding_rate(symbol: str) -> dict[str, Any] | None:
    try:
        history = _get(
            BINANCE_FUTURES_URL,
            "/fapi/v1/fundingRate",
            {"symbol": symbol, "limit": 1},
        )
        if not history:
            return None
        latest = history[0]
        mark = _get(
            BINANCE_FUTURES_URL,
            "/fapi/v1/premiumIndex",
            {"symbol": symbol},
        )
        return {
            "rate": float(latest["fundingRate"]),
            "rate_percent": float(latest["fundingRate"]) * 100,
            "next_funding_time": pd.to_datetime(int(latest["fundingTime"]), unit="ms"),
            "mark_price": float(mark.get("markPrice", 0)),
            "index_price": float(mark.get("indexPrice", 0)),
        }
    except (requests.HTTPError, BinanceDataError):
        return None


def fetch_open_interest(symbol: str) -> float | None:
    try:
        data = _get(BINANCE_FUTURES_URL, "/fapi/v1/openInterest", {"symbol": symbol})
        return float(data["openInterest"])
    except (requests.HTTPError, BinanceDataError):
        return None


def fetch_open_interest_history(symbol: str, period: str = "1h", limit: int = 48) -> list[dict]:
    try:
        data = _get(
            BINANCE_FUTURES_URL,
            "/futures/data/openInterestHist",
            {"symbol": symbol, "period": period, "limit": min(limit, 500)},
        )
        return [
            {
                "time": int(row["timestamp"]) // 1000,
                "sumOpenInterest": float(row["sumOpenInterest"]),
                "sumOpenInterestValue": float(row.get("sumOpenInterestValue", 0)),
            }
            for row in data
        ]
    except (requests.HTTPError, BinanceDataError):
        return []


def fetch_btc_change_24h() -> float | None:
    try:
        t = fetch_ticker_24h("BTCUSDT")
        return float(t.get("priceChangePercent", 0))
    except (requests.HTTPError, BinanceDataError):
        return None


def fetch_funding_history(symbol: str, limit: int = 90) -> list[dict]:
    """История фандинга для графика (как CoinGlass)."""
    try:
        history = _get(
            BINANCE_FUTURES_URL,
            "/fapi/v1/fundingRate",
            {"symbol": symbol, "limit": min(limit, 1000)},
        )
        points = []
        for row in sorted(history, key=lambda x: int(x["fundingTime"])):
            rate_pct = float(row["fundingRate"]) * 100
            points.append(
                {
                    "time": int(row["fundingTime"]) // 1000,
                    "value": round(rate_pct, 4),
                }
            )
        return points
    except (requests.HTTPError, BinanceDataError):
        return []


def validate_symbol(symbol: str) -> bool:
    try:
        _get(BINANCE_SPOT_URL, "/api/v3/ticker/price", {"symbol": symbol})
        return True
    except (requests.HTTPError, BinanceDataError):
        return False
