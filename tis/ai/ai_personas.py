"""AI-персоны инвесторов: один и тот же инструмент глазами разных стилей.

Идея (вдохновлено мульти-агентными терминалами): берём уже посчитанный анализ
(тренд, RSI, волатильность, уровни, фандинг, новости) и просим AI оценить его
с позиции конкретной инвест-философии. Каждая персона — это системная установка
(стиль + критерии), а не отдельная модель. Работает на BYOK-ключе пользователя.

Честность важнее «вау»: напр. стоимостной инвестор по мем-коину должен сказать
«спекуляция, не моё», а не выдавать фальшивый бычий сигнал.
"""

from __future__ import annotations

import json
import os

from tis.ai.ai_news import AIChatError, _extract_json, request_chat  # общий запросчик с fallback

_DEFAULT_MODEL = "gpt-4o-mini"


class PersonaError(Exception):
    pass


# id -> метаданные и инструкция стиля (ru/en).
PERSONAS: dict[str, dict] = {
    "value": {
        "name_ru": "Уоррен Баффет", "name_en": "Warren Buffett", "emoji": "🛡️",
        "tag_ru": "Стоимость и качество", "tag_en": "Value & quality",
        "style_ru": "Ты — стоимостной инвестор уровня Баффета. Смотришь на долгосрочную ценность, понятность актива, запас прочности и устойчивость тренда. К хайпу и чистой спекуляции (мем-коины, перегретые активы) относишься скептически и честно говоришь, если актив «не твой».",
        "style_en": "You are a Buffett-style value investor. You focus on long-term value, understandability, margin of safety and trend durability. You are skeptical of hype and pure speculation (meme coins, overheated assets) and honestly say when an asset is 'not for you'.",
    },
    "growth": {
        "name_ru": "Питер Линч", "name_en": "Peter Lynch", "emoji": "🚀",
        "tag_ru": "Рост по разумной цене", "tag_en": "Growth at reasonable price",
        "style_ru": "Ты — инвестор роста в стиле Питера Линча (GARP). Ищешь сильный импульс и растущий тренд, но не любишь переплачивать на перекупленности. Ценишь подтверждение объёмом и согласие таймфреймов.",
        "style_en": "You are a Lynch-style growth investor (GARP). You look for strong momentum and rising trend, but dislike overpaying on overbought levels. You value volume confirmation and timeframe agreement.",
    },
    "deepvalue": {
        "name_ru": "Бенджамин Грэм", "name_en": "Benjamin Graham", "emoji": "📉",
        "tag_ru": "Запас прочности", "tag_en": "Margin of safety",
        "style_ru": "Ты — осторожный инвестор в стиле Грэма. Главное — сохранение капитала и запас прочности. Покупаешь только у поддержки/перепроданности, избегаешь перегретых активов. Если риск высокий — рекомендуешь ждать.",
        "style_en": "You are a cautious Graham-style investor. Priority is capital preservation and margin of safety. You buy only near support/oversold, avoid overheated assets. If risk is high, you recommend waiting.",
    },
    "trader": {
        "name_ru": "Скальпер-трейдер", "name_en": "Momentum trader", "emoji": "⚡",
        "tag_ru": "Техника и импульс", "tag_en": "Technicals & momentum",
        "style_ru": "Ты — краткосрочный трейдер. Решаешь по технике: тренд, MACD, RSI, ADX, уровни, имбаланс, объём, фандинг. Даёшь конкретику по входу/риску. Долгосрочная «ценность» тебя не интересует.",
        "style_en": "You are a short-term trader. You decide purely on technicals: trend, MACD, RSI, ADX, levels, imbalance, volume, funding. You give concrete entry/risk takes. Long-term 'value' doesn't interest you.",
    },
    "macro": {
        "name_ru": "Макро-стратег", "name_en": "Macro strategist", "emoji": "🌍",
        "tag_ru": "Сверху вниз, риск-он/офф", "tag_en": "Top-down, risk-on/off",
        "style_ru": "Ты — макро-стратег. Смотришь сверху вниз: общий риск-аппетит, волатильность, новостной фон, корреляции. Оцениваешь, благоприятен ли сейчас фон для этого класса актива.",
        "style_en": "You are a macro strategist. Top-down view: overall risk appetite, volatility, news backdrop, correlations. You assess whether the current backdrop favors this asset class.",
    },
}


def personas_meta(lang: str = "ru") -> list[dict]:
    out = []
    for pid, p in PERSONAS.items():
        out.append({
            "id": pid,
            "name": p["name_en"] if lang == "en" else p["name_ru"],
            "tag": p["tag_en"] if lang == "en" else p["tag_ru"],
            "emoji": p["emoji"],
        })
    return out


def _fmt(v, suffix="") -> str:
    return f"{v}{suffix}" if v is not None else "—"


def build_snapshot(a: dict, lang: str = "ru") -> str:
    """Компактная текстовая сводка анализа для модели."""
    tfs = a.get("timeframes") or []
    tf_line = "; ".join(
        f'{t.get("timeframe","").upper()}: {t.get("trend","")} RSI {t.get("rsi","?")} ADX {t.get("adx","?")} MACD {t.get("macd_trend","")}'
        for t in tfs
    )
    vol = a.get("volatility") or {}
    fund = a.get("funding") or {}
    news = a.get("news") or {}
    acc = a.get("accuracy") or {}
    sup = ", ".join(str(x) for x in (a.get("support_levels") or [])[:3])
    res = ", ".join(str(x) for x in (a.get("resistance_levels") or [])[:3])
    imb = a.get("imbalances") or []

    L = (lambda ru, en: en if lang == "en" else ru)
    lines = [
        f'{L("Инструмент","Instrument")}: {a.get("display_name") or a.get("symbol")} ({a.get("market_type")})',
        f'{L("Цена","Price")}: {a.get("price")} ({a.get("change_24h_pct")}% 24h)',
        f'{L("Общий тренд","Overall trend")}: {a.get("overall_trend")} — {a.get("trend_summary")}',
        f'{L("Таймфреймы","Timeframes")}: {tf_line}',
        f'{L("Волатильность","Volatility")}: {vol.get("level","?")} (ATR {vol.get("atr_percent","?")}%)',
        f'{L("Сопротивления","Resistances")}: {res or "—"}',
        f'{L("Поддержки","Supports")}: {sup or "—"}',
    ]
    if fund:
        lines.append(f'{L("Фандинг","Funding")}: {fund.get("rate_percent","?")}% — {fund.get("sentiment","")}')
    if news and news.get("total"):
        lines.append(f'{L("Новостной фон","News mood")}: {news.get("good",0)}↑ / {news.get("bad",0)}↓ — {news.get("label","")}')
    if imb:
        lines.append(f'{L("Имбалансов рядом","Imbalances nearby")}: {len(imb)}')
    if acc:
        lines.append(f'{L("Балл согласованности","Agreement score")}: {acc.get("overall_pct","?")}/100')
    return "\n".join(lines)


def _build_prompt(persona: dict, snapshot: str, lang: str) -> str:
    style = persona["style_en"] if lang == "en" else persona["style_ru"]
    if lang == "en":
        return (
            f"{style}\n\nMarket snapshot:\n{snapshot}\n\n"
            "Give YOUR verdict in this persona's voice. Return STRICT JSON:\n"
            '{"verdict":"buy|hold|avoid","confidence":0-100,'
            '"horizon":"short/mid/long-term","summary":"1-2 sentences in your voice",'
            '"pros":["..."],"cons":["..."]}\n'
            "Be honest: if the asset doesn't fit your style, say so via verdict=avoid/hold. Answer in English."
        )
    return (
        f"{style}\n\nСводка по рынку:\n{snapshot}\n\n"
        "Дай СВОЙ вердикт в духе этой персоны. Верни СТРОГО JSON:\n"
        '{"verdict":"buy|hold|avoid","confidence":0-100,'
        '"horizon":"краткосрок/среднесрок/долгосрок","summary":"1-2 предложения от твоего лица",'
        '"pros":["..."],"cons":["..."]}\n'
        "Будь честен: если актив не в твоём стиле — скажи это через verdict=avoid/hold. Отвечай по-русски."
    )


def analyze_persona(
    persona_id: str,
    snapshot: str,
    lang: str = "ru",
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    persona = PERSONAS.get(persona_id)
    if not persona:
        raise PersonaError("Неизвестная персона")
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise PersonaError("Не задан AI-ключ")

    base = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    model = model or os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)
    prompt = _build_prompt(persona, snapshot, lang)

    try:
        content = request_chat(base, key, model, prompt, temperature=0.3)
        parsed = json.loads(_extract_json(content))
    except AIChatError as e:
        raise PersonaError(str(e)) from e
    except (ValueError, TypeError) as e:
        raise PersonaError(f"Не удалось разобрать ответ модели: {e}") from e

    verdict = str(parsed.get("verdict", "hold")).lower()
    if verdict not in ("buy", "hold", "avoid"):
        verdict = "hold"
    return {
        "persona": persona_id,
        "name": persona["name_en"] if lang == "en" else persona["name_ru"],
        "emoji": persona["emoji"],
        "verdict": verdict,
        "confidence": parsed.get("confidence", 0),
        "horizon": str(parsed.get("horizon", "")).strip(),
        "summary": str(parsed.get("summary", "")).strip(),
        "pros": [str(x).strip() for x in (parsed.get("pros") or []) if str(x).strip()][:4],
        "cons": [str(x).strip() for x in (parsed.get("cons") or []) if str(x).strip()][:4],
        "model": model,
    }
