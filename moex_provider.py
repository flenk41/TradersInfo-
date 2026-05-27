"""Данные российских акций с MOEX ISS API (без ключей)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from net import request_with_retry

_MOEX = "https://iss.moex.com/iss"
_TIMEOUT = 25

_INTERVAL_MAP = {
    "5m": 10,
    "15m": 10,
    "1h": 60,
    "4h": 60,
    "1d": 24,
}

# Свечей примерно за один календарный день (с учётом выходных) по интервалам MOEX.
_PER_CAL_DAY = {1: 400.0, 10: 90.0, 60: 14.0, 24: 0.72}


def _secid(symbol: str) -> str:
    return symbol.upper().replace(".ME", "").replace(".MC", "").strip()


def _moex_from(moex_interval: int, base_limit: int) -> str:
    """Дата начала окна под нужное число свечей.

    ISS отдаёт максимум 500 свечей с начала диапазона (самые старые). Слишком
    широкое окно вернёт прошлогодние свечи, поэтому окно считаем от limit и
    держим итог заведомо ниже страницы в 500 строк.
    """
    per = _PER_CAL_DAY.get(moex_interval, 14.0)
    days = max(3, int(base_limit / per * 1.6) + 3)
    max_days = max(3, int(480 / per))
    days = min(days, max_days)
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def fetch_klines_moex(symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    secid = _secid(symbol)
    moex_interval = _INTERVAL_MAP.get(interval, 60)
    base_limit = limit * 4 if interval == "4h" else limit
    start = _moex_from(moex_interval, base_limit)

    url = (
        f"{_MOEX}/engines/stock/markets/shares/securities/{secid}/candles.json"
        f"?interval={moex_interval}&from={start}"
    )
    r = request_with_retry(url, timeout=_TIMEOUT, source="MOEX")
    data = r.json()
    rows = data.get("candles", {}).get("data", [])
    cols = data.get("candles", {}).get("columns", [])
    if not rows:
        raise ValueError(f"Нет данных MOEX для {secid}")

    df = pd.DataFrame(rows, columns=cols)
    df = df.rename(
        columns={
            "begin": "open_time",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
    )
    df["open_time"] = pd.to_datetime(df["open_time"])
    df["quote_volume"] = df["close"] * df["volume"]
    df = df.tail(limit).reset_index(drop=True)

    if interval == "4h" and moex_interval == 60:
        d = df.set_index("open_time")
        o = d.resample("4h").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "quote_volume": "sum",
            }
        ).dropna()
        df = o.reset_index()

    return df[["open_time", "open", "high", "low", "close", "volume", "quote_volume"]]


def fetch_ticker_moex(symbol: str) -> dict[str, Any]:
    secid = _secid(symbol)
    url = (
        f"{_MOEX}/engines/stock/markets/shares/boards/TQBR/securities/{secid}.json"
    )
    r = request_with_retry(url, timeout=_TIMEOUT, source="MOEX")
    payload = r.json()
    market = payload.get("marketdata", {})
    cols = market.get("columns", [])
    rows = market.get("data", [])
    if not rows:
        raise ValueError(f"Нет котировки MOEX для {secid}")

    row = dict(zip(cols, rows[0]))

    def _f(key: str, default: float = 0.0) -> float:
        v = row.get(key)
        if v is None:
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    last = _f("LAST") or _f("MARKETPRICE") or _f("LCURRENTPRICE") or _f("CLOSEPRICE")
    if last <= 0:
        hist = fetch_klines_moex(secid, "1d", 3)
        last = float(hist["close"].iloc[-1]) if len(hist) else 0
    change = _f("LASTCHANGEPRCNT") or _f("CHANGE")
    high = _f("HIGH") or last
    low = _f("LOW") or last
    vol = _f("VALTODAY") or _f("VOLTODAY")

    return {
        "lastPrice": last,
        "priceChangePercent": change,
        "highPrice": high,
        "lowPrice": low,
        "quoteVolume": vol,
    }


def validate_moex(symbol: str) -> bool:
    try:
        fetch_ticker_moex(symbol)
        return True
    except Exception:
        return False
