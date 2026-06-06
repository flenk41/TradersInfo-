"""Фундаментальные показатели акций через Yahoo Finance (yfinance .info).

Бесплатно, без ключа. Работает в первую очередь для акций США; для крипты/форекса
неприменимо, для части RU-бумаг данные у Yahoo могут отсутствовать — тогда честно
возвращаем available=False. Используется и в карточке «Фундаментал», и подмешивается
в персоны Баффета/Линча/Грэма (реальные P/E, маржа, рост вместо одного графика).
"""

from __future__ import annotations

from tis.core.net import retry_call

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

    from tis.data.instruments_catalog import get_instrument, resolve_yf_symbol

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

    from tis.data.instruments_catalog import get_instrument, resolve_yf_symbol

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


def _ticker_info(pair: str, market: str):
    """(yf.Ticker, info) или (None, None). Общий помощник для качества/держателей."""
    if market != "stock" or yf is None:
        return None, None
    from tis.data.instruments_catalog import resolve_yf_symbol

    yf_sym = resolve_yf_symbol(pair, market)
    try:
        t = yf.Ticker(yf_sym)
        info = retry_call(lambda: t.info, source=f"Yahoo info ({yf_sym})", max_retries=2)
    except Exception:
        return None, None
    if not info or not isinstance(info, dict):
        return t, None
    return t, info


def fetch_quality_scorecard(pair: str, market: str, lang: str = "ru") -> dict:
    """Чек-лист «качество бизнеса» в духе Баффета/Грэма: ROE, долг, маржа, рост,
    FCF, P/E, earnings yield, ликвидность. Сырые цифры → ✓/~/✗ + композитный балл."""
    _t, info = _ticker_info(pair, market)
    if not info:
        return {"available": False}
    L = (lambda ru, en: en if lang == "en" else ru)
    checks: list[dict] = []

    def add(name, val, good, ok, fmt, higher=True, detail=""):
        v = _num(val)
        if v is None:
            return
        if higher:
            status = "good" if v >= good else ("ok" if v >= ok else "bad")
        else:
            status = "good" if v <= good else ("ok" if v <= ok else "bad")
        checks.append({"name": name, "value": fmt(v), "status": status, "detail": detail})

    roe = info.get("returnOnEquity")
    add(L("ROE (отдача на капитал)", "ROE"), roe, 0.15, 0.10, lambda v: f"{v*100:.1f}%",
        detail=L("≥15% — сильный бизнес", "≥15% is strong"))
    add(L("Маржа прибыли", "Profit margin"), info.get("profitMargins"), 0.15, 0.07, lambda v: f"{v*100:.1f}%")
    add(L("Операц. маржа", "Operating margin"), info.get("operatingMargins"), 0.15, 0.07, lambda v: f"{v*100:.1f}%")
    # debtToEquity у Yahoo в процентах (50 = 0.5x). Меньше — лучше.
    add(L("Долг / капитал", "Debt / equity"), info.get("debtToEquity"), 60, 120, lambda v: f"{v/100:.2f}x", higher=False,
        detail=L("<0.6x — низкий долг", "<0.6x is low debt"))
    add(L("Текущая ликвидность", "Current ratio"), info.get("currentRatio"), 1.5, 1.0, lambda v: f"{v:.2f}")
    add(L("Рост выручки", "Revenue growth"), info.get("revenueGrowth"), 0.08, 0.0, lambda v: f"{v*100:.1f}%")
    add(L("Рост прибыли", "Earnings growth"), info.get("earningsGrowth"), 0.08, 0.0, lambda v: f"{v*100:.1f}%")
    # earnings yield = 1/PE; сравниваем с ~бескупонной доходностью.
    pe = _num(info.get("trailingPE"))
    if pe and pe > 0:
        ey = 1 / pe
        checks.append({
            "name": L("Доходность прибыли (E/P)", "Earnings yield (E/P)"),
            "value": f"{ey*100:.1f}%",
            "status": "good" if ey >= 0.06 else ("ok" if ey >= 0.04 else "bad"),
            "detail": L("выше доходности облигаций — привлекательно", "above bond yield is attractive"),
        })
    add(L("P/E", "P/E"), pe, 22, 35, lambda v: f"{v:.1f}", higher=False)
    add(L("P/B", "P/B"), info.get("priceToBook"), 4, 8, lambda v: f"{v:.1f}", higher=False)
    fcf = _num(info.get("freeCashflow"))
    if fcf is not None:
        checks.append({
            "name": L("Свободный денежный поток", "Free cash flow"),
            "value": _fmt_big(fcf), "status": "good" if fcf > 0 else "bad",
            "detail": L("положительный FCF — бизнес генерит кэш", "positive FCF — cash-generative"),
        })

    if not checks:
        return {"available": False}
    good = sum(1 for c in checks if c["status"] == "good")
    ok = sum(1 for c in checks if c["status"] == "ok")
    n = len(checks)
    score = round((good + ok * 0.5) / n * 100)
    if score >= 70:
        grade, label = "A", L("Качественный бизнес", "Quality business")
    elif score >= 50:
        grade, label = "B", L("Средний — выборочно", "Average — selective")
    else:
        grade, label = "C", L("Слабый / спекулятивный", "Weak / speculative")
    return {
        "available": True, "score": score, "grade": grade, "label": label,
        "passed": good, "total": n, "checks": checks,
    }


def fetch_top_holders(pair: str, market: str) -> dict:
    """Крупные держатели (13F/институционалы) + доли инсайдеров/институтов."""
    t, info = _ticker_info(pair, market)
    if t is None:
        return {"available": False}
    pct_inst = _num((info or {}).get("heldPercentInstitutions"))
    pct_ins = _num((info or {}).get("heldPercentInsiders"))
    top: list[dict] = []
    try:
        ih = t.institutional_holders
        if ih is not None and hasattr(ih, "iterrows"):
            cols = {c.lower(): c for c in ih.columns}
            hcol = cols.get("holder")
            pcol = cols.get("pctheld") or cols.get("% out")
            vcol = cols.get("value")
            for _, row in ih.head(8).iterrows():
                holder = str(row[hcol]) if hcol else None
                if not holder:
                    continue
                pct = _num(row[pcol]) if pcol else None
                if pct is not None and pct <= 1:
                    pct = pct * 100  # доля -> %
                top.append({
                    "holder": holder,
                    "pct": round(pct, 2) if pct is not None else None,
                    "value": _fmt_big(_num(row[vcol])) if vcol and _num(row[vcol]) is not None else None,
                })
    except Exception:
        pass
    if pct_inst is None and pct_ins is None and not top:
        return {"available": False}
    return {
        "available": True,
        "pct_institutions": round(pct_inst * 100, 1) if pct_inst is not None else None,
        "pct_insiders": round(pct_ins * 100, 1) if pct_ins is not None else None,
        "top": top,
    }


def fundamentals_line(pair: str, market: str, lang: str = "ru") -> str:
    """Однострочная сводка для подмешивания в AI-персону. Пусто при отсутствии."""
    data = fetch_fundamentals(pair, market, lang)
    if not data.get("available"):
        return ""
    parts = [f'{i["name"]}: {i["value"]}' for i in data.get("items", [])[:6]]
    head = data.get("sector", "")
    return (f'{head}. ' if head else "") + "; ".join(parts)
