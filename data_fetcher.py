"""Получение рыночных данных с Binance."""

from __future__ import annotations

from typing import Any

import pandas as pd
import requests

from config import BINANCE_FUTURES_URL, BINANCE_SPOT_URL, DEFAULT_QUOTE


class BinanceDataError(Exception):
    pass


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
    response = requests.get(f"{url}{path}", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


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
    except requests.HTTPError:
        return None


def fetch_open_interest(symbol: str) -> float | None:
    try:
        data = _get(BINANCE_FUTURES_URL, "/fapi/v1/openInterest", {"symbol": symbol})
        return float(data["openInterest"])
    except requests.HTTPError:
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
    except requests.HTTPError:
        return []


def fetch_btc_change_24h() -> float | None:
    try:
        t = fetch_ticker_24h("BTCUSDT")
        return float(t.get("priceChangePercent", 0))
    except requests.HTTPError:
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
    except requests.HTTPError:
        return []


def validate_symbol(symbol: str) -> bool:
    try:
        _get(BINANCE_SPOT_URL, "/api/v3/ticker/price", {"symbol": symbol})
        return True
    except requests.HTTPError:
        return False
