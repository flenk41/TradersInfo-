"""Единый доступ к данным: крипто, акции, валюта."""

from __future__ import annotations

from typing import Any

import pandas as pd

from data_fetcher import (
    BinanceDataError,
    fetch_btc_change_24h,
    fetch_funding_history as _fetch_funding_binance,
    fetch_funding_rate,
    fetch_klines as _fetch_klines_binance,
    fetch_open_interest,
    fetch_open_interest_history,
    fetch_ticker_24h as _fetch_ticker_binance,
    validate_symbol as _validate_binance,
)
from markets import MarketDataError, detect_market, normalize_pair
from yfinance_provider import (
    fetch_klines_yf,
    fetch_ticker_24h_yf,
    validate_symbol_yf,
)


def fetch_klines(pair: str, interval: str = "1h", limit: int = 200, market: str | None = None) -> pd.DataFrame:
    m = detect_market(pair, market)
    sym, _ = normalize_pair(pair, m)
    if m == "crypto":
        return _fetch_klines_binance(sym, interval, limit)
    from instruments_catalog import get_instrument, resolve_yf_symbol

    inst = get_instrument(pair, m) if m == "stock" else None
    if inst and inst.region == "ru":
        from moex_provider import fetch_klines_moex

        return fetch_klines_moex(inst.id, interval, limit)
    yf_sym = resolve_yf_symbol(pair, m) if m == "stock" else sym
    return fetch_klines_yf(yf_sym, interval, limit)


def fetch_ticker_24h(pair: str, market: str | None = None) -> dict[str, Any]:
    m = detect_market(pair, market)
    sym, _ = normalize_pair(pair, m)
    if m == "crypto":
        return _fetch_ticker_binance(sym)
    from instruments_catalog import get_instrument, resolve_yf_symbol

    inst = get_instrument(pair, m) if m == "stock" else None
    if inst and inst.region == "ru":
        from moex_provider import fetch_ticker_moex

        return fetch_ticker_moex(inst.id)
    yf_sym = resolve_yf_symbol(pair, m) if m == "stock" else sym
    return fetch_ticker_24h_yf(yf_sym)


def validate_symbol(pair: str, market: str | None = None) -> bool:
    m = detect_market(pair, market)
    sym, _ = normalize_pair(pair, m)
    try:
        if m == "crypto":
            return _validate_binance(sym)
        from instruments_catalog import get_instrument, resolve_yf_symbol

        inst = get_instrument(pair, m) if m == "stock" else None
        if inst and inst.region == "ru":
            from moex_provider import validate_moex

            return validate_moex(inst.id)
        yf_sym = resolve_yf_symbol(pair, m) if m == "stock" else sym
        return validate_symbol_yf(yf_sym)
    except Exception:
        return False


def fetch_funding_history(pair: str, limit: int = 90, market: str | None = None) -> list[dict]:
    m = detect_market(pair, market)
    if m != "crypto":
        return []
    sym, _ = normalize_pair(pair, m)
    return _fetch_funding_binance(sym, limit)


def get_funding_rate(pair: str, market: str | None = None):
    m = detect_market(pair, market)
    if m != "crypto":
        return None
    sym, _ = normalize_pair(pair, m)
    return fetch_funding_rate(sym)


def get_open_interest(pair: str, market: str | None = None):
    m = detect_market(pair, market)
    if m != "crypto":
        return None
    sym, _ = normalize_pair(pair, m)
    return fetch_open_interest(sym)


def get_open_interest_history(pair: str, market: str | None = None):
    m = detect_market(pair, market)
    if m != "crypto":
        return []
    sym, _ = normalize_pair(pair, m)
    return fetch_open_interest_history(sym)
