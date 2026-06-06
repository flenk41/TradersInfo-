"""Единый доступ к данным: крипто, акции, валюта."""

from __future__ import annotations

from typing import Any

import pandas as pd

from tis.data.data_fetcher import (
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
from tis.core.markets import MarketDataError, detect_market, normalize_pair
from tis.data.yfinance_provider import (
    fetch_klines_yf,
    fetch_ticker_24h_yf,
    validate_symbol_yf,
)


def _is_moex(pair: str, market: str) -> bool:
    """Любая бумага с суффиксом .ME — это MOEX (а не только из каталога)."""
    return market == "stock" and pair.strip().upper().endswith(".ME")


# Котировочные суффиксы Binance, которые нужно отбросить при переводе в Yahoo-символ.
_CRYPTO_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USD")


def _crypto_to_yf(sym: str) -> str:
    """BTCUSDT -> BTC-USD (Yahoo котирует крипту к USD; доступен в РФ без VPN)."""
    s = sym.strip().upper()
    for q in _CRYPTO_QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return f"{s[:-len(q)]}-USD"
    return f"{s}-USD"


def _use_bybit(source: str | None) -> bool:
    return (source or "").strip().lower() == "bybit"


def fetch_klines(pair: str, interval: str = "1h", limit: int = 200, market: str | None = None, source: str | None = None) -> pd.DataFrame:
    m = detect_market(pair, market)
    sym, _ = normalize_pair(pair, m)
    if m == "crypto":
        if _use_bybit(source):
            from tis.data.bybit_provider import BybitDataError, fetch_klines as _fk_bybit
            try:
                return _fk_bybit(sym, interval, limit)
            except BybitDataError:
                pass  # Bybit не отдал — падаем на общий путь ниже
        try:
            return _fetch_klines_binance(sym, interval, limit)
        except BinanceDataError:
            # Binance недоступен (блокировка/обрыв) — берём крипту с Yahoo.
            return fetch_klines_yf(_crypto_to_yf(sym), interval, limit)
    if _is_moex(pair, m):
        from tis.data.moex_provider import fetch_klines_moex

        return fetch_klines_moex(pair, interval, limit)
    from tis.data.instruments_catalog import resolve_yf_symbol

    yf_sym = resolve_yf_symbol(pair, m) if m == "stock" else sym
    return fetch_klines_yf(yf_sym, interval, limit)


def fetch_ticker_24h(pair: str, market: str | None = None, source: str | None = None) -> dict[str, Any]:
    m = detect_market(pair, market)
    sym, _ = normalize_pair(pair, m)
    if m == "crypto":
        if _use_bybit(source):
            from tis.data.bybit_provider import BybitDataError, fetch_ticker_24h as _ft_bybit
            try:
                return _ft_bybit(sym)
            except BybitDataError:
                pass
        try:
            return _fetch_ticker_binance(sym)
        except BinanceDataError:
            return fetch_ticker_24h_yf(_crypto_to_yf(sym))
    if _is_moex(pair, m):
        from tis.data.moex_provider import fetch_ticker_moex

        return fetch_ticker_moex(pair)
    from tis.data.instruments_catalog import resolve_yf_symbol

    yf_sym = resolve_yf_symbol(pair, m) if m == "stock" else sym
    return fetch_ticker_24h_yf(yf_sym)


def validate_symbol(pair: str, market: str | None = None) -> bool:
    m = detect_market(pair, market)
    sym, _ = normalize_pair(pair, m)
    try:
        if m == "crypto":
            try:
                if _validate_binance(sym):
                    return True
            except BinanceDataError:
                pass
            # Binance недоступен или символ не найден — пробуем Yahoo.
            return validate_symbol_yf(_crypto_to_yf(sym))
        if _is_moex(pair, m):
            from tis.data.moex_provider import validate_moex

            return validate_moex(pair)
        from tis.data.instruments_catalog import resolve_yf_symbol

        yf_sym = resolve_yf_symbol(pair, m) if m == "stock" else sym
        return validate_symbol_yf(yf_sym)
    except Exception:
        return False


def fetch_funding_history(pair: str, limit: int = 90, market: str | None = None, source: str | None = None) -> list[dict]:
    m = detect_market(pair, market)
    if m != "crypto":
        return []
    sym, _ = normalize_pair(pair, m)
    if _use_bybit(source):
        from tis.data.bybit_provider import fetch_funding_history as _fh_bybit
        pts = _fh_bybit(sym, limit)
        if pts:
            return pts
    return _fetch_funding_binance(sym, limit)


def get_funding_rate(pair: str, market: str | None = None, source: str | None = None):
    m = detect_market(pair, market)
    if m != "crypto":
        return None
    sym, _ = normalize_pair(pair, m)
    if _use_bybit(source):
        from tis.data.bybit_provider import fetch_funding_rate as _fr_bybit
        r = _fr_bybit(sym)
        if r:
            return r
    return fetch_funding_rate(sym)


def get_open_interest(pair: str, market: str | None = None, source: str | None = None):
    m = detect_market(pair, market)
    if m != "crypto":
        return None
    sym, _ = normalize_pair(pair, m)
    if _use_bybit(source):
        from tis.data.bybit_provider import fetch_open_interest as _oi_bybit
        v = _oi_bybit(sym)
        if v is not None:
            return v
    return fetch_open_interest(sym)


def get_open_interest_history(pair: str, market: str | None = None, source: str | None = None):
    m = detect_market(pair, market)
    if m != "crypto":
        return []
    sym, _ = normalize_pair(pair, m)
    if _use_bybit(source):
        from tis.data.bybit_provider import fetch_open_interest_history as _oih_bybit
        pts = _oih_bybit(sym)
        if pts:
            return pts
    return fetch_open_interest_history(sym)
