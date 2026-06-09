"""Короткий кэш ответов API (снижает повторные запросы к биржам)."""

from __future__ import annotations

import time
from typing import Any, Callable

_TTL_SEC = 50
_store: dict[str, tuple[float, Any]] = {}


def get_cached(key: str, loader: Callable[[], Any], ttl: float = _TTL_SEC) -> Any:
    now = time.time()
    hit = _store.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = loader()
    _store[key] = (now, value)
    return value


def peek(key: str, ttl: float = _TTL_SEC) -> Any | None:
    """Вернуть значение из кэша, если оно свежее, иначе None — БЕЗ вычисления.

    В отличие от get_cached не запускает loader на промахе. Нужно там, где
    дорого считать на каждый промах (напр. скринер не должен гонять полный
    analyze_pair по всей вселенной — берёт балл, только если он уже в кэше)."""
    hit = _store.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    return None


def invalidate(prefix: str | None = None) -> None:
    if prefix is None:
        _store.clear()
        return
    for k in list(_store.keys()):
        if k.startswith(prefix):
            del _store[k]
