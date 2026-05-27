"""Сетевой слой с ретраями и обработкой 429/451 для всех провайдеров данных.

Единая точка для повторов: сетевые сбои и 5xx повторяем с экспоненциальным
backoff, 429/418 уважаем Retry-After, 451 (геоблок) сразу отдаём понятной ошибкой.
Binance-провайдер исторически имеет свою копию этой логики в data_fetcher.py.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import requests

_DEFAULT_TIMEOUT = 20
_DEFAULT_RETRIES = 3
_BACKOFF_BASE = 0.6  # сек; 0.6, 1.2, 2.4 ...
_MAX_BACKOFF = 5.0

_session = requests.Session()


class DataSourceError(Exception):
    """Базовая ошибка источника данных."""


class RateLimitedError(DataSourceError):
    """HTTP 429/418 — слишком много запросов."""


class GeoBlockedError(DataSourceError):
    """HTTP 451 — доступ заблокирован для региона/IP."""


def _sleep_backoff(attempt: int, retry_after: str | None = None) -> None:
    if retry_after and retry_after.isdigit():
        time.sleep(min(float(retry_after), _MAX_BACKOFF))
    else:
        time.sleep(min(_BACKOFF_BASE * (2 ** attempt), _MAX_BACKOFF))


def request_with_retry(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_RETRIES,
    source: str = "источник",
) -> requests.Response:
    """GET с ретраями. Кидает GeoBlockedError/RateLimitedError/DataSourceError."""
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            resp = _session.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                _sleep_backoff(attempt)
                continue
            raise DataSourceError(f"{source}: сеть недоступна ({exc})") from exc

        status = resp.status_code

        if status == 451:
            raise GeoBlockedError(
                f"{source}: доступ заблокирован для этого IP/региона (HTTP 451). "
                "На облачном хостинге используйте прокси или другой источник."
            )

        if status in (418, 429):
            if attempt < max_retries - 1:
                _sleep_backoff(attempt, resp.headers.get("Retry-After"))
                continue
            raise RateLimitedError(
                f"{source}: превышена частота запросов (HTTP {status}). Подождите и повторите."
            )

        if status >= 500:
            last_exc = requests.HTTPError(f"HTTP {status}", response=resp)
            if attempt < max_retries - 1:
                _sleep_backoff(attempt)
                continue
            resp.raise_for_status()

        resp.raise_for_status()
        return resp

    if last_exc:
        raise DataSourceError(f"{source}: {last_exc}") from last_exc
    raise DataSourceError(f"{source}: не удалось получить данные")


def retry_call(
    fn: Callable[[], Any],
    *,
    max_retries: int = _DEFAULT_RETRIES,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    source: str = "источник",
) -> Any:
    """Повторяет вызов fn() при исключениях (для библиотек без HTTP-кодов, напр. yfinance)."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except exceptions as exc:  # noqa: BLE001 — намеренно широкий повтор
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(min(_BACKOFF_BASE * (2 ** attempt), _MAX_BACKOFF))
                continue
            raise DataSourceError(f"{source}: {exc}") from exc
    if last_exc:
        raise DataSourceError(f"{source}: {last_exc}") from last_exc
    raise DataSourceError(f"{source}: не удалось получить данные")
