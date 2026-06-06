"""AI-разбор новостей через OpenAI.

Ключевой принцип: модель НЕ придумывает ссылки. Мы отдаём ей пронумерованный
список уже полученных реальных новостей, просим ссылаться на номера, а ссылки
подставляем сами из исходного списка — поэтому каждая ссылка гарантированно настоящая.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

_DEFAULT_MODEL = "gpt-4o-mini"
_TIMEOUT = 45


class AINewsError(Exception):
    pass


def is_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _host_of(base: str) -> str:
    try:
        return base.split("//", 1)[1].split("/", 1)[0]
    except Exception:
        return base


def _provider_error(resp, base: str) -> str:
    """Понятное сообщение об ошибке провайдера с указанием реального адреса."""
    host = _host_of(base)
    code = resp.status_code
    text = (resp.text or "")[:200]
    is_openai = "openai.com" in host
    if code == 401:
        return f"Неверный AI-ключ (401) для {host}. Проверьте ключ в «🔑 AI-ключ»."
    if code == 429 or "quota" in text.lower() or "resource_exhausted" in text.lower():
        if is_openai:
            return ("OpenAI: квота исчерпана — у OpenAI нет бесплатного тарифа. "
                    "Возьмите БЕСПЛАТНЫЙ ключ Groq или Gemini в «🔑 AI-ключ».")
        return (f"{host}: превышен лимит запросов (429). Подождите ~1 минуту и повторите. "
                f"Если повторяется — проверьте лимиты ключа. Ответ: {text}")
    if code == 404:
        return f"{host}: модель не найдена (404). Проверьте название модели. Ответ: {text}"
    return f"AI-провайдер {host} ответил {code}: {text}"


class AIChatError(Exception):
    """Ошибка обращения к AI-провайдеру (с готовым понятным текстом)."""


# Статический запас на случай, если живой список не удалось получить.
_OPENROUTER_FREE_FALLBACKS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "google/gemma-2-9b-it:free",
    "mistralai/mistral-7b-instruct:free",
]

# Кэш живого списка бесплатных моделей OpenRouter (роста меняется часто).
_or_models_cache = {"ts": 0.0, "models": []}


def _openrouter_free_models(base: str, key: str) -> list[str]:
    """Живой список бесплатных моделей OpenRouter (pricing == 0), кэш 1 час."""
    now = time.time()
    if _or_models_cache["models"] and now - _or_models_cache["ts"] < 3600:
        return _or_models_cache["models"]
    try:
        r = requests.get(
            f"{base.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
        data = r.json().get("data", [])
        free = []
        for m in data:
            mid = m.get("id") or ""
            pr = m.get("pricing", {}) or {}
            zero = lambda v: str(v) in ("0", "0.0", "0.00")
            if ":free" in mid and zero(pr.get("prompt")) and zero(pr.get("completion")):
                free.append(mid)
        if free:
            _or_models_cache["models"] = free[:10]
            _or_models_cache["ts"] = now
        return _or_models_cache["models"] or free
    except Exception:
        return []


def _is_rate_limited(resp) -> bool:
    t = (resp.text or "").lower()
    return resp.status_code == 429 or "rate-limit" in t or "rate_limit" in t or "rate limited" in t


def request_chat(base: str, key: str, model: str, prompt: str, temperature: float = 0.2) -> str:
    """POST /chat/completions с двумя подстраховками:
    1) если модель не знает response_format — повтор без него;
    2) на OpenRouter, если бесплатная модель перегружена (429), перебираем
       другие бесплатные модели, пока одна не ответит.
    Возвращает content-строку или кидает AIChatError с понятным текстом.
    """
    base = (base or "").rstrip("/")
    is_or = "openrouter.ai" in base
    models = [model]
    if is_or:
        # живой список бесплатных моделей + статический запас
        candidates = _openrouter_free_models(base, key) or _OPENROUTER_FREE_FALLBACKS
        for m in candidates:
            if m not in models:
                models.append(m)

    def _post(m, use_json):
        payload = {"model": m, "messages": [{"role": "user", "content": prompt}], "temperature": temperature}
        if use_json:
            payload["response_format"] = {"type": "json_object"}
        # 2 попытки на случай временного сетевого/SSL-сбоя.
        last_exc = None
        for attempt in range(2):
            try:
                return requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=_TIMEOUT,
                )
            except requests.RequestException as e:
                last_exc = e
                if attempt == 0:
                    time.sleep(1.0)
        raise last_exc

    host = _host_of(base)
    last = None
    for m in models:
        try:
            resp = _post(m, True)
            if resp.status_code == 400 and "response_format" in resp.text.lower():
                resp = _post(m, False)
        except requests.RequestException as e:
            raise AIChatError(
                f"Не удаётся подключиться к {host} (сеть/SSL: {type(e).__name__}). "
                f"Похоже, провайдер недоступен из вашей сети. Попробуйте Gemini или Ollama в «🔑 AI-ключ»."
            ) from e
        if resp.status_code == 200:
            try:
                return resp.json()["choices"][0]["message"]["content"]
            except (KeyError, ValueError, TypeError) as e:
                raise AIChatError(f"Не удалось разобрать ответ модели: {e}") from e
        last = resp
        # на OpenRouter перебираем дальше при перегрузке (429), «модель недоступна»
        # (404 No endpoints) И при сбое апстрим-провайдера (5xx, напр. 502) —
        # пропускаем мёртвые/перегруженные free-модели, пока одна не ответит.
        if not (is_or and (_is_rate_limited(resp) or resp.status_code == 404 or resp.status_code >= 500)):
            break
    raise AIChatError(_provider_error(last, base))


def _extract_json(text: str) -> str:
    """Достаёт JSON-объект из ответа модели (на случай ```json ... ``` или лишнего текста)."""
    t = (text or "").strip()
    if "```" in t:
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    return t[start : end + 1] if start != -1 and end > start else t


def _fmt_date(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m")
    except Exception:
        return ""


def _build_prompt(name: str, market: str, items: list[dict], lang: str = "ru") -> str:
    lines = []
    for i, n in enumerate(items, 1):
        lines.append(f'{i}. [{_fmt_date(n.get("timestamp", 0))}] {n.get("title", "")} — {n.get("source", "")}')
    news_block = "\n".join(lines)
    if lang == "en":
        return (
            f"You are a financial analyst. Based ONLY on the news list below for the instrument "
            f"{name} ({market}), assess the market sentiment. Do not invent facts or add links — "
            f"reference only the news item numbers from the list.\n\n"
            f"News:\n{news_block}\n\n"
            "Return STRICT JSON with the schema:\n"
            '{"overall":"bullish|bearish|neutral","confidence":0-100,'
            '"summary":"2-3 sentences overall conclusion",'
            '"bullish":[{"point":"short factor","refs":[news numbers]}],'
            '"bearish":[{"point":"short factor","refs":[news numbers]}]}\n'
            "Every point MUST contain refs — numbers of supporting news. "
            "If there are no factors, return an empty array. Answer in English."
        )
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


def analyze_news(
    name: str,
    market: str,
    items: list[dict],
    max_items: int = 30,
    lang: str = "ru",
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    # Ключ/эндпоинт/модель: сначала переданные пользователем (BYOK), иначе из окружения.
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise AINewsError("Не задан AI-ключ — нажмите «🔑 AI-ключ» и вставьте свой бесплатный ключ")
    if not items:
        raise AINewsError("Нет новостей для анализа")

    used = items[:max_items]
    base = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    model = model or os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)
    prompt = _build_prompt(name, market, used, lang)

    try:
        content = request_chat(base, key, model, prompt)
        parsed = json.loads(_extract_json(content))
    except AIChatError as e:
        raise AINewsError(str(e)) from e
    except (ValueError, TypeError) as e:
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
