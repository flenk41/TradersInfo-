"""Фундаментальные показатели акций через Yahoo Finance (yfinance .info).

Бесплатно, без ключа. Работает в первую очередь для акций США; для крипты/форекса
неприменимо, для части RU-бумаг данные у Yahoo могут отсутствовать — тогда честно
возвращаем available=False. Используется и в карточке «Фундаментал», и подмешивается
в персоны Баффета/Линча/Грэма (реальные P/E, маржа, рост вместо одного графика).
"""

from __future__ import annotations

from net import retry_call

try:
    import yfinance as yf
except ImportError:
    yf = None


# поле yfinance -> (ключ, имя ru, имя en, тип форматирования)
_FIELDS = [
    ("marketCap", "mcap", "Капитализация", "Market cap", "big"),
    ("trailingPE", "pe", "P/E", "P/E", "num"),
    ("forwardPE", "fpe", "P/E (форвард)", "Forward P/E", "num"),
    ("priceToBook", "pb", "P/B", "P/B", "num"),
    ("trailingAnnualDividendYield", "div", "Дивиденды", "Dividend yield", "pct"),
    ("profitMargins", "margin", "Маржа прибыли", "Profit margin", "pct"),
    ("revenueGrowth", "revg", "Рост выручки", "Revenue growth", "pct"),
    ("returnOnEquity", "roe", "ROE", "ROE", "pct"),
    ("debtToEquity", "de", "Долг/капитал", "Debt/Equity", "num"),
    ("beta", "beta", "Бета", "Beta", "num"),
]


def _fmt_big(v: float) -> str:
    a = abs(v)
    if a >= 1e12:
        return f"{v / 1e12:.2f}T"
    if a >= 1e9:
        return f"{v / 1e9:.2f}B"
    if a >= 1e6:
        return f"{v / 1e6:.2f}M"
    return f"{v:.0f}"


def _format(kind: str, v) -> str | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    if kind == "big":
        return _fmt_big(f)
    if kind == "pct":          # доля 0..1 -> %
        return f"{f * 100:.1f}%"
    if kind == "pct_raw":      # yfinance dividendYield иногда уже в %, иногда доля
        return f"{(f * 100 if f < 1 else f):.2f}%"
    return f"{f:.2f}"


def fetch_fundamentals(pair: str, market: str, lang: str = "ru") -> dict:
    if market != "stock":
        return {"available": False, "reason": "only_stocks"}
    if yf is None:
        return {"available": False, "reason": "no_yfinance"}

    from instruments_catalog import get_instrument, resolve_yf_symbol

    yf_sym = resolve_yf_symbol(pair, market)
    inst = get_instrument(pair, market)

    try:
        info = retry_call(lambda: yf.Ticker(yf_sym).info, source=f"Yahoo info ({yf_sym})", max_retries=2)
    except Exception:
        info = None
    if not info or not isinstance(info, dict):
        return {"available": False, "reason": "no_data"}

    items = []
    for field, key, name_ru, name_en, kind in _FIELDS:
        val = _format(kind, info.get(field))
        if val is not None:
            items.append({"key": key, "name": name_en if lang == "en" else name_ru, "value": val})

    sector = info.get("sector") or ""
    industry = info.get("industry") or ""
    name = (inst.name if inst else None) or info.get("shortName") or pair

    if not items and not sector:
        return {"available": False, "reason": "no_data"}

    return {
        "available": True,
        "name": name,
        "sector": sector,
        "industry": industry,
        "items": items,
        "summary": info.get("longBusinessSummary", "")[:280] if info.get("longBusinessSummary") else "",
    }


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # отбрасываем NaN


def fetch_dividend_info(pair: str, market: str) -> dict:
    """Числовые данные для калькулятора дивидендов: цена, дивиденд на акцию, доходность.

    Только акции. Дивиденд на акцию — годовой (trailingAnnualDividendRate, в валюте
    бумаги). Если Yahoo не отдал что-то одно — досчитываем из доходности и цены.
    """
    if market != "stock":
        return {"available": False, "reason": "only_stocks"}
    if yf is None:
        return {"available": False, "reason": "no_yfinance"}

    from instruments_catalog import get_instrument, resolve_yf_symbol

    yf_sym = resolve_yf_symbol(pair, market)
    inst = get_instrument(pair, market)
    try:
        info = retry_call(lambda: yf.Ticker(yf_sym).info, source=f"Yahoo info ({yf_sym})", max_retries=2)
    except Exception:
        info = None
    if not info or not isinstance(info, dict):
        return {"available": False, "reason": "no_data"}

    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice")) or _num(info.get("previousClose"))
    dps = _num(info.get("trailingAnnualDividendRate"))
    dyield = _num(info.get("trailingAnnualDividendYield"))
    if dps is None and dyield is not None and price:
        dps = round(price * dyield, 4)
    if dyield is None and dps is not None and price:
        dyield = dps / price

    name = (inst.name if inst else None) or info.get("shortName") or pair
    return {
        "available": True,
        "name": name,
        "currency": info.get("currency") or "",
        "price": price,
        "dividend_per_share": dps,
        "dividend_yield": dyield,
    }


def fundamentals_line(pair: str, market: str, lang: str = "ru") -> str:
    """Однострочная сводка для подмешивания в AI-персону. Пусто при отсутствии."""
    data = fetch_fundamentals(pair, market, lang)
    if not data.get("available"):
        return ""
    parts = [f'{i["name"]}: {i["value"]}' for i in data.get("items", [])[:6]]
    head = data.get("sector", "")
    return (f'{head}. ' if head else "") + "; ".join(parts)
