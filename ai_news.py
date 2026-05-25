"""AI-разбор новостей через OpenAI.

Ключевой принцип: модель НЕ придумывает ссылки. Мы отдаём ей пронумерованный
список уже полученных реальных новостей, просим ссылаться на номера, а ссылки
подставляем сами из исходного списка — поэтому каждая ссылка гарантированно настоящая.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

_DEFAULT_MODEL = "gpt-4o-mini"
_TIMEOUT = 45


class AINewsError(Exception):
    pass


def is_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _fmt_date(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m")
    except Exception:
        return ""


def _build_prompt(name: str, market: str, items: list[dict]) -> str:
    lines = []
    for i, n in enumerate(items, 1):
        lines.append(f'{i}. [{_fmt_date(n.get("timestamp", 0))}] {n.get("title", "")} — {n.get("source", "")}')
    news_block = "\n".join(lines)
    return (
        f"Ты — финансовый аналитик. На основе ТОЛЬКО списка новостей ниже по инструменту "
        f"{name} ({market}) оцени рыночный настрой. Не выдумывай факты и не добавляй ссылок — "
        f"ссылайся только на номера новостей из списка.\n\n"
        f"Новости:\n{news_block}\n\n"
        "Верни СТРОГО JSON по схеме:\n"
        '{"overall":"bullish|bearish|neutral","confidence":0-100,'
        '"summary":"2-3 предложения общего вывода",'
        '"bullish":[{"point":"кратко фактор","refs":[номера новостей]}],'
        '"bearish":[{"point":"кратко фактор","refs":[номера новостей]}]}\n'
        "Каждый пункт ОБЯЗАН содержать refs — номера подтверждающих новостей. "
        "Если факторов нет, верни пустой массив. Отвечай по-русски."
    )


def analyze_news(name: str, market: str, items: list[dict], max_items: int = 30) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise AINewsError("Не задан OPENAI_API_KEY — добавьте ключ в .env")
    if not items:
        raise AINewsError("Нет новостей для анализа")

    used = items[:max_items]
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)

    try:
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": _build_prompt(name, market, used)}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        raise AINewsError(f"Сеть/таймаут к OpenAI: {e}") from e

    if resp.status_code != 200:
        raise AINewsError(f"OpenAI {resp.status_code}: {resp.text[:160]}")

    try:
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, ValueError, TypeError) as e:
        raise AINewsError(f"Не удалось разобрать ответ модели: {e}") from e

    def _map(points) -> list[dict]:
        out = []
        for p in points or []:
            sources = []
            for r in p.get("refs") or []:
                try:
                    idx = int(r) - 1
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < len(used):
                    n = used[idx]
                    sources.append({"title": n["title"], "link": n["link"], "source": n["source"]})
            point = str(p.get("point", "")).strip()
            if point:
                out.append({"point": point, "sources": sources})
        return out

    overall = str(parsed.get("overall", "neutral")).lower()
    if overall not in ("bullish", "bearish", "neutral"):
        overall = "neutral"

    return {
        "overall": overall,
        "confidence": parsed.get("confidence", 0),
        "summary": str(parsed.get("summary", "")).strip(),
        "bullish": _map(parsed.get("bullish")),
        "bearish": _map(parsed.get("bearish")),
        "model": model,
        "analyzed_count": len(used),
    }
