"""Новости по инструменту через Google News RSS + простая разметка тональности."""

from __future__ import annotations

import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

from tis.core.net import request_with_retry

_GN = "https://news.google.com/rss/search"
_TIMEOUT = 8
_HEADERS = {"User-Agent": "Mozilla/5.0"}

# Подстроки (рус + англ). Совпадение по вхождению, чтобы ловить словоформы.
_POS = [
    "рост", "выро", "подорож", "укреп", "прибыл", "рекорд", "ралли", "дивиденд",
    "покупа", "обнови", "максимум", "оптимизм", "восстанов", "отскок", "разгон",
    "gain", "surge", "rally", "beat", "record", "profit", "jump", "soar",
    "upgrade", "bullish", "rise", "rose", "growth", "boost", "rebound", "outperform",
]
_NEG = [
    "паде", "упал", "сниж", "обвал", "убыт", "санкц", "дефолт", "кризис",
    "распрод", "давлени", "подешев", "ослаб", "минимум", "просад", "крах", "риск",
    "drop", "fall", "plunge", "crash", "loss", "miss", "downgrade", "bearish",
    "slump", "decline", "selloff", "sell-off", "warning", "tumble", "slide", "weak",
]


def _sentiment(title: str) -> tuple[str, int]:
    t = title.lower()
    pos = sum(1 for w in _POS if w in t)
    neg = sum(1 for w in _NEG if w in t)
    if pos > neg:
        return "good", pos - neg
    if neg > pos:
        return "bad", neg - pos
    return "neutral", 0


def build_query(pair: str, market: str, lang: str = "ru") -> str:
    from tis.data.instruments_catalog import get_instrument

    inst = get_instrument(pair, market)
    name = inst.name if inst else pair
    if lang == "en":
        if market == "crypto":
            return f"{name} cryptocurrency"
        if market == "forex":
            p = pair.upper().replace("=X", "")
            return f"{p} forex"
        return f"{name} stock"
    if market == "crypto":
        return f"{name} криптовалюта"
    if market == "forex":
        p = pair.upper().replace("=X", "")
        return f"{p} курс валют"
    return f"{name} акции"


def sentiment_counts(items: list[dict], window_days: int = 7) -> dict:
    """Сводка новостного фона за окно: счётчики и нормированный net (-1..1)."""
    now = time.time()
    span = window_days * 86400
    recent = [n for n in items if n.get("timestamp") and now - n["timestamp"] <= span]
    good = sum(1 for n in recent if n["sentiment"] == "good")
    bad = sum(1 for n in recent if n["sentiment"] == "bad")
    total = len(recent)
    net = round((good - bad) / total, 2) if total else 0.0
    if net >= 0.15:
        label = "позитивный"
    elif net <= -0.15:
        label = "негативный"
    else:
        label = "нейтральный"
    return {
        "good": good,
        "bad": bad,
        "neutral": total - good - bad,
        "total": total,
        "net": net,
        "label": label,
        "window_days": window_days,
    }


def fetch_news(query: str, limit: int = 60, lang: str = "ru", max_retries: int = 3) -> list[dict]:
    locale = (
        {"hl": "en-US", "gl": "US", "ceid": "US:en"}
        if lang == "en"
        else {"hl": "ru", "gl": "RU", "ceid": "RU:ru"}
    )
    url = _GN + "?" + urllib.parse.urlencode({"q": query, **locale})
    r = request_with_retry(url, headers=_HEADERS, timeout=_TIMEOUT, source="Google News", max_retries=max_retries)
    root = ET.fromstring(r.content)

    items: list[dict] = []
    for it in root.findall(".//item")[:limit]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        source = src_el.text.strip() if src_el is not None and src_el.text else ""
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()

        ts = 0
        pub = it.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ts = int(dt.timestamp())
        except Exception:
            ts = 0

        sentiment, score = _sentiment(title)
        items.append(
            {
                "title": title,
                "link": link,
                "source": source,
                "timestamp": ts,
                "sentiment": sentiment,
                "score": score,
            }
        )
    return items
