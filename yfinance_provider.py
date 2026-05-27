"""Данные акций и Forex через Yahoo Finance."""

from __future__ import annotations

from typing import Any

import pandas as pd

from net import retry_call

try:
    import yfinance as yf
except ImportError:
    yf = None

_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "1h",
    "1d": "1d",
}


def _require_yf():
    if yf is None:
        raise ImportError("Установите yfinance: pip install yfinance")


def fetch_klines_yf(symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    _require_yf()
    yf_interval = _INTERVAL_MAP.get(interval, "1h")
    if yf_interval in ("1m", "5m", "15m"):
        period = "60d"
    elif yf_interval == "1h":
        period = "730d"
    else:
        period = "5y"

    ticker = yf.Ticker(symbol)
    df = retry_call(
        lambda: ticker.history(period=period, interval=yf_interval, auto_adjust=True),
        source=f"Yahoo Finance ({symbol})",
    )
    if df.empty:
        raise ValueError(f"Нет данных для {symbol}")

    df = df.reset_index()
    col = "Datetime" if "Datetime" in df.columns else "Date"
    df["open_time"] = pd.to_datetime(df[col])
    if df["open_time"].dt.tz is not None:
        df["open_time"] = df["open_time"].dt.tz_localize(None)

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df["quote_volume"] = df["close"] * df["volume"]
    df = df.tail(limit).reset_index(drop=True)

    if interval == "4h" and yf_interval == "1h":
        df = _resample_4h(df)

    return df[["open_time", "open", "high", "low", "close", "volume", "quote_volume"]]


def _resample_4h(df: pd.DataFrame) -> pd.DataFrame:
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
    return o.reset_index()


def fetch_ticker_24h_yf(symbol: str) -> dict[str, Any]:
    _require_yf()
    t = yf.Ticker(symbol)
    hist = retry_call(
        lambda: t.history(period="5d", interval="1h", auto_adjust=True),
        source=f"Yahoo Finance ({symbol})",
    )
    if hist.empty:
        info = t.fast_info
        price = float(getattr(info, "last_price", 0) or 0)
        return {
            "lastPrice": price,
            "priceChangePercent": 0.0,
            "highPrice": price,
            "lowPrice": price,
            "quoteVolume": 0,
        }
    last = float(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
    chg = ((last - prev) / prev) * 100 if prev else 0
    return {
        "lastPrice": last,
        "priceChangePercent": chg,
        "highPrice": float(hist["High"].tail(24).max()),
        "lowPrice": float(hist["Low"].tail(24).min()),
        "quoteVolume": float((hist["Close"] * hist["Volume"]).tail(24).sum()),
    }


def validate_symbol_yf(symbol: str) -> bool:
    try:
        df = fetch_klines_yf(symbol, "1d", 5)
        return len(df) > 0
    except Exception:
        return False
