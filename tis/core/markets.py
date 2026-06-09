"""Типы рынков и нормализация символов."""

from __future__ import annotations

from tis.core.config import DEFAULT_QUOTE


class MarketDataError(Exception):
    pass


def detect_market(pair: str, market: str | None = None) -> str:
    if market in ("crypto", "stock", "forex"):
        return market
    p = pair.strip().upper()
    if "/" in p and "USDT" not in p and "USD" in p:
        return "forex"
    if p.endswith("=X") or p in ("EURUSD", "GBPUSD", "USDJPY"):
        return "forex"
    if "/" in p and "USDT" in p:
        return "crypto"
    if p.endswith(".ME") or p.endswith(".ME".upper()):
        return "stock"
    if len(p) <= 6 and p.replace(".", "").isalpha():
        return "stock"
    return "crypto"


def normalize_pair(pair: str, market: str, quote: str = DEFAULT_QUOTE) -> tuple[str, str]:
    """Возвращает (symbol для API, отображаемое имя)."""
    cleaned = pair.strip().upper().replace(" ", "")

    if market == "crypto":
        from tis.data.data_fetcher import normalize_symbol

        sym = normalize_symbol(pair, quote)
        if "/" in pair.upper():
            display = pair.upper().replace("-", "/")
        else:
            display = f"{sym[:-4]}/{quote}" if sym.endswith(quote) else sym
        return sym, display

    if market == "forex":
        if "/" in cleaned:
            base, q = cleaned.split("/", 1)
            sym = f"{base}{q}=X"
            display = f"{base}/{q}"
        elif cleaned.endswith("=X"):
            sym = cleaned
            display = cleaned.replace("=X", "").replace("USD", "/USD")[:7]
        else:
            sym = f"{cleaned}=X" if len(cleaned) == 6 else f"{cleaned}USD=X"
            display = pair.upper()
        return sym, display

    # stocks
    from tis.data.instruments_catalog import get_instrument, resolve_yf_symbol

    inst = get_instrument(pair, "stock")
    if inst:
        sym = inst.yf_symbol or inst.id
        display = f"{inst.name} ({inst.id.replace('.ME', '')})"
        return sym, display

    sym = resolve_yf_symbol(pair, "stock")
    if sym.endswith(".ME"):
        display = sym.replace(".ME", "")
    else:
        display = sym
    return sym, display


_NASDAQ_TICKERS = frozenset(
    {"AAPL", "MSFT", "NVDA", "AMD", "META", "GOOGL", "GOOG", "AMZN", "INTC", "NFLX"}
)


def to_tradingview_symbol(pair: str, market: str | None = None) -> str:
    """Символ для виджета TradingView Advanced Chart."""
    m = detect_market(pair, market)
    sym, display = normalize_pair(pair, m)

    if m == "crypto":
        return f"BINANCE:{sym}"

    if m == "stock":
        from tis.data.instruments_catalog import get_instrument

        inst = get_instrument(pair, "stock")
        if inst and inst.tv_exchange:
            tv_sym = inst.id.replace(".ME", "")
            return f"{inst.tv_exchange}:{tv_sym}"
        if sym.endswith(".ME"):
            return f"MOEX:{sym.replace('.ME', '')}"
        exchange = "NASDAQ" if sym in _NASDAQ_TICKERS else "NYSE"
        return f"{exchange}:{sym}"

    if m == "forex":
        fx = display.replace("/", "").replace("=X", "")
        if len(fx) == 6:
            return f"FX:{fx}"
        return f"FX:{sym.replace('=X', '')}"

    return f"BINANCE:{sym}"
