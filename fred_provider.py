"""Макро-фон через FRED (Federal Reserve Economic Data).

Бесплатный ключ: fred.stlouisfed.org/docs/api/api_key.html → переменная FRED_API_KEY.
Данные публичные, один ключ обслуживает весь инстанс (как опциональный серверный
ресурс). Без ключа эндпоинт честно просит его настроить.

Берём ключевые индикаторы, которые двигают весь рынок: ставка ФРС, инфляция,
доходности, индекс доллара, безработица, кривая доходности и VIX (индекс страха).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from net import request_with_retry

_FRED = "https://api.stlouisfed.org/fred/series/observations"

# key -> (series_id, имя ru/en, единица, тип)
_SERIES = [
    ("fedrate", "DFF", "Ставка ФРС", "Fed rate", "%", "rate"),
    ("cpi", "CPIAUCSL", "Инфляция (CPI г/г)", "Inflation (CPI YoY)", "%", "cpi"),
    ("dgs10", "DGS10", "Доходность 10 лет", "10Y yield", "%", "rate"),
    ("t10y2y", "T10Y2Y", "Кривая 10л−2л", "Yield curve 10Y−2Y", "%", "curve"),
    ("dollar", "DTWEXBGS", "Индекс доллара", "Dollar index", "", "level"),
    ("unrate", "UNRATE", "Безработица", "Unemployment", "%", "rate"),
    ("vix", "VIXCLS", "VIX (индекс страха)", "VIX (fear index)", "", "vix"),
]


def is_configured() -> bool:
    return bool(os.environ.get("FRED_API_KEY"))


def _observations(series_id: str, limit: int, key: str) -> list[float]:
    """Последние значения серии (новые → старые), пропуская пропуски '.'."""
    url = (
        f"{_FRED}?series_id={series_id}&api_key={key}&file_type=json"
        f"&sort_order=desc&limit={limit}"
    )
    r = request_with_retry(url, timeout=15, source="FRED")
    rows = r.json().get("observations", [])
    out: list[float] = []
    for o in rows:
        v = o.get("value", ".")
        if v not in (".", "", None):
            try:
                out.append(float(v))
            except ValueError:
                pass
    return out


def _one(meta, key: str) -> dict | None:
    skey, sid, name_ru, name_en, unit, kind = meta
    try:
        if kind == "cpi":
            obs = _observations(sid, 13, key)  # для г/г нужно ~13 мес
            if len(obs) < 13:
                return None
            latest, year_ago = obs[0], obs[12]
            value = (latest / year_ago - 1) * 100 if year_ago else 0.0
            prev_obs = _observations(sid, 14, key)
            prev = (prev_obs[1] / prev_obs[13] - 1) * 100 if len(prev_obs) >= 14 and prev_obs[13] else value
            change = value - prev
        else:
            obs = _observations(sid, 2, key)
            if not obs:
                return None
            value = obs[0]
            change = obs[0] - obs[1] if len(obs) > 1 else 0.0
        return {
            "key": skey,
            "name_ru": name_ru,
            "name_en": name_en,
            "unit": unit,
            "kind": kind,
            "value": round(value, 2),
            "change": round(change, 2),
        }
    except Exception:
        return None


def _summary(items: dict, lang: str) -> tuple[str, str]:
    """Короткий вывод о риск-аппетите + метка (risk-on / risk-off / mixed)."""
    vix = items.get("vix", {}).get("value")
    curve = items.get("t10y2y", {}).get("value")
    fed = items.get("fedrate", {})
    risk_off = 0
    notes_ru, notes_en = [], []

    if vix is not None:
        if vix >= 25:
            risk_off += 1
            notes_ru.append(f"VIX {vix} — высокий страх")
            notes_en.append(f"VIX {vix} — high fear")
        elif vix <= 15:
            risk_off -= 1
            notes_ru.append(f"VIX {vix} — спокойствие")
            notes_en.append(f"VIX {vix} — calm")
    if curve is not None and curve < 0:
        risk_off += 1
        notes_ru.append("кривая доходности инвертирована (риск рецессии)")
        notes_en.append("inverted yield curve (recession risk)")
    if fed.get("change", 0) > 0:
        notes_ru.append("ставка ФРС растёт (жёстче условия)")
        notes_en.append("Fed rate rising (tighter)")
    elif fed.get("change", 0) < 0:
        notes_ru.append("ставка ФРС снижается (мягче условия)")
        notes_en.append("Fed rate falling (easier)")

    if risk_off >= 1:
        label_ru, label_en, cls = "Risk-off (осторожно)", "Risk-off (cautious)", "off"
    elif risk_off <= -1:
        label_ru, label_en, cls = "Risk-on (аппетит к риску)", "Risk-on", "on"
    else:
        label_ru, label_en, cls = "Смешанный фон", "Mixed backdrop", "mixed"

    text = ("; ".join(notes_en) if lang == "en" else "; ".join(notes_ru)) or (
        "no clear signals" if lang == "en" else "явных сигналов нет"
    )
    return (label_en if lang == "en" else label_ru), f"{cls}|{text}"


def fetch_macro(lang: str = "ru", api_key: str | None = None) -> dict:
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED не настроен")
    items: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=7) as pool:
        for res in pool.map(lambda m: _one(m, key), _SERIES):
            if res:
                items[res["key"]] = res

    # Пусто = ключ неверный или FRED недоступен — честно сообщаем об ошибке.
    if not items:
        raise RuntimeError("FRED не вернул данных — проверьте ключ (неверный или не активирован)")

    label, packed = _summary(items, lang)
    cls, note = packed.split("|", 1)
    ordered = [items[k] for (k, *_rest) in _SERIES if k in items]
    return {
        "items": [
            {
                "key": it["key"],
                "name": it["name_en"] if lang == "en" else it["name_ru"],
                "value": it["value"],
                "unit": it["unit"],
                "change": it["change"],
                "kind": it["kind"],
            }
            for it in ordered
        ],
        "label": label,
        "risk": cls,
        "note": note,
    }


def macro_line(lang: str = "ru", api_key: str | None = None) -> str:
    """Однострочная сводка макро для подмешивания в AI-персону. Тихо пустая при сбое."""
    try:
        m = fetch_macro(lang, api_key)
    except Exception:
        return ""
    parts = [f'{i["name"]}: {i["value"]}{i["unit"]}' for i in m["items"][:5]]
    return f'{m["label"]} — ' + "; ".join(parts)
