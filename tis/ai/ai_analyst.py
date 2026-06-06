# SPDX-License-Identifier: AGPL-3.0-or-later
"""AI-аналитик: связное ИИ-заключение по НАШЕМУ просчитанному анализу.

Два уровня:
- "simple" — короткое понятное заключение для новичка (что делать и почему);
- "full"   — развёрнутый разбор по полному снимку анализа + биржевым данным
             Bybit (фандинг/открытый интерес) и, если переданы, открытым
             позициям пользователя на этом инструменте.

Работает на BYOK-ключе (OpenAI-совместимый). Модель НЕ исполняет сделки —
только текстовое заключение поверх уже посчитанных индикаторов.
"""

from __future__ import annotations

import json
import os

from tis.ai.ai_news import AIChatError, _extract_json, request_chat

_DEFAULT_MODEL = "gpt-4o-mini"


class AnalystError(Exception):
    pass


def _fmt(v, suffix=""):
    return f"{v}{suffix}" if v is not None else "—"


def _clean_text(text: str) -> str:
    """Очистка свободного ответа модели: убираем <think>…</think>, ```fences``` и хвосты."""
    import re

    t = text or ""
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = t.replace("```json", "").replace("```", "")
    return t.strip()


def build_analyst_snapshot(a: dict, lang: str, level: str, source: str | None, positions: list | None) -> str:
    """Текстовый снимок анализа для модели. Для full — максимально подробный."""
    L = (lambda ru, en: en if lang == "en" else ru)
    src_label = "Bybit" if (source or "").lower() == "bybit" else "Binance/Yahoo"
    trade = a.get("trade") or {}
    acc = a.get("accuracy") or {}
    vol = a.get("volatility") or {}
    fund = a.get("funding") or {}
    deep = a.get("deep") or {}

    lines = [
        f'{L("Инструмент","Instrument")}: {a.get("display_name") or a.get("symbol")} ({a.get("market_type")})',
        f'{L("Источник данных","Data source")}: {src_label}',
        f'{L("Цена","Price")}: {a.get("price")} ({a.get("change_24h_pct")}% 24h)',
        f'{L("Общий тренд","Overall trend")}: {a.get("overall_trend")} — {a.get("trend_summary")}',
        f'{L("Балл согласованности","Agreement score")}: {acc.get("overall_pct","?")}/100 '
        f'({L("рекоменд.","rec.")}: {acc.get("recommended_side","wait")})',
        f'{L("Вердикт движка","Engine verdict")}: ЛОНГ {trade.get("long_verdict","?")} ({trade.get("long_score","?")}), '
        f'ШОРТ {trade.get("short_verdict","?")} ({trade.get("short_score","?")})',
    ]

    if level == "full":
        tfs = a.get("timeframes") or []
        tf_line = "; ".join(
            f'{t.get("timeframe","").upper()}: {t.get("trend","")} RSI {t.get("rsi","?")} ADX {t.get("adx","?")} MACD {t.get("macd_trend","")}'
            for t in tfs
        )
        sup = ", ".join(str(x) for x in (a.get("support_levels") or [])[:3])
        res = ", ".join(str(x) for x in (a.get("resistance_levels") or [])[:3])
        lines += [
            f'{L("Таймфреймы","Timeframes")}: {tf_line}',
            f'{L("Волатильность","Volatility")}: {vol.get("level","?")} (ATR {vol.get("atr_percent","?")}%)',
            f'{L("Сопротивления","Resistances")}: {res or "—"}',
            f'{L("Поддержки","Supports")}: {sup or "—"}',
        ]
        if deep:
            lines.append(
                f'{L("Режим","Regime")}: {deep.get("market_regime","?")} · '
                f'{L("Риск","Risk")} {deep.get("risk_score","?")}/100 · '
                f'{L("схождение","confluence")} L{deep.get("confluence_long","?")}/S{deep.get("confluence_short","?")}'
            )
        # Биржевые данные Bybit: фандинг и открытый интерес — важный сентимент перпетуала.
        if fund:
            lines.append(
                f'{L("Фандинг","Funding")}: {fund.get("rate_percent","?")}% — {fund.get("sentiment","")} '
                f'(OI {_fmt(fund.get("open_interest"))})'
            )
        scalp = a.get("scalp") or {}
        if scalp.get("verdict"):
            lines.append(f'{L("Скальпинг","Scalping")}: {scalp.get("verdict")}')
        news = a.get("news") or {}
        if news and news.get("total"):
            lines.append(f'{L("Новости","News")}: {news.get("good",0)}↑/{news.get("bad",0)}↓ — {news.get("label","")}')

    # Открытые позиции пользователя на этом инструменте (если переданы).
    if positions:
        for p in positions[:3]:
            lines.append(
                f'{L("Открыта позиция","Open position")}: {p.get("side","").upper()} {p.get("symbol")} '
                f'{L("вход","entry")} {p.get("entry_price")}, {L("плечо","lev")} {p.get("leverage")}x, '
                f'PnL {p.get("unrealized_pnl")}'
            )

    return "\n".join(lines)


def _build_prompt(snapshot: str, lang: str, level: str, has_positions: bool) -> str:
    if lang == "en":
        depth = (
            "Give a SHORT, beginner-friendly take: what to do and why, in plain words."
            if level == "simple"
            else "Give a thorough professional read: synthesize timeframes, funding/OI, levels and risk."
        )
        pos = " Comment on the user's open position(s) too." if has_positions else ""
        return (
            f"You are a disciplined trading analyst. {depth}{pos}\n\n"
            f"Analysis snapshot:\n{snapshot}\n\n"
            "Return STRICT JSON:\n"
            '{"action":"long|short|wait","confidence":0-100,"horizon":"intraday/swing",'
            '"summary":"2-3 sentences","key_points":["..."],"risks":["..."],'
            '"plan":"one sentence entry/stop/target idea"}\n'
            "Be honest and risk-aware. If signals conflict, prefer wait. Answer in English."
        )
    depth = (
        "Дай КОРОТКОЕ понятное новичку заключение: что делать и почему, простыми словами."
        if level == "simple"
        else "Дай развёрнутый профессиональный разбор: синтез таймфреймов, фандинга/OI, уровней и риска."
    )
    pos = " Прокомментируй и открытые позиции пользователя." if has_positions else ""
    return (
        f"Ты — дисциплинированный торговый аналитик. {depth}{pos}\n\n"
        f"Снимок анализа:\n{snapshot}\n\n"
        "Верни СТРОГО JSON:\n"
        '{"action":"long|short|wait","confidence":0-100,"horizon":"внутридень/свинг",'
        '"summary":"2-3 предложения","key_points":["..."],"risks":["..."],'
        '"plan":"одно предложение: идея входа/стопа/цели"}\n'
        "Будь честен и риск-ориентирован. При противоречии сигналов выбирай wait. Отвечай по-русски."
    )


def analyze_market(
    snapshot: str,
    lang: str = "ru",
    level: str = "full",
    has_positions: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise AnalystError("Не задан AI-ключ")
    base = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    model = model or os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)
    prompt = _build_prompt(snapshot, lang, level, has_positions)
    try:
        content = request_chat(base, key, model, prompt, temperature=0.3)
    except AIChatError as e:
        raise AnalystError(str(e)) from e

    # Часть бесплатных моделей игнорирует «строгий JSON» и отдаёт текст (или
    # вовсе пустой ответ). Пытаемся распарсить JSON; если не вышло — не падаем,
    # а используем текст модели как заключение.
    parsed = None
    try:
        parsed = json.loads(_extract_json(content))
        if not isinstance(parsed, dict):
            parsed = None
    except (ValueError, TypeError):
        parsed = None

    if parsed is None:
        txt = _clean_text(content)
        if not txt:
            raise AnalystError(
                "Модель вернула пустой ответ. Попробуйте ещё раз или выберите другую модель в «🔑 AI-ключ»."
            )
        return {
            "level": level, "action": "wait", "confidence": 0, "horizon": "",
            "summary": txt[:700], "key_points": [], "risks": [], "plan": "",
            "model": model, "freeform": True,
        }

    action = str(parsed.get("action", "wait")).lower()
    if action not in ("long", "short", "wait"):
        action = "wait"
    return {
        "level": level,
        "action": action,
        "confidence": parsed.get("confidence", 0),
        "horizon": str(parsed.get("horizon", "")).strip(),
        "summary": str(parsed.get("summary", "")).strip(),
        "key_points": [str(x).strip() for x in (parsed.get("key_points") or []) if str(x).strip()][:5],
        "risks": [str(x).strip() for x in (parsed.get("risks") or []) if str(x).strip()][:4],
        "plan": str(parsed.get("plan", "")).strip(),
        "model": model,
    }
