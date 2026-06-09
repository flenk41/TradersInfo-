# SPDX-License-Identifier: AGPL-3.0-or-later
"""Приватные READ-ONLY данные аккаунта Bybit V5 (баланс, позиции).

BYOK: ключ/секрет приходят в теле запроса от браузера, используются только для
подписи конкретного запроса и НИГДЕ не сохраняются (ни в файлы, ни в логи).
Реализованы ТОЛЬКО эндпоинты чтения (wallet-balance, position/list) — никаких
ордеров, переводов и выводов (operator-safety). Подпись HMAC-SHA256 по схеме
Bybit V5: sign = HMAC(secret, timestamp + api_key + recv_window + query).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import requests

_BASE = "https://api.bybit.com"
_RECV_WINDOW = "5000"
_TIMEOUT = 20


class BybitAuthError(Exception):
    pass


def _signed_get(path: str, query: str, api_key: str, api_secret: str) -> dict:
    ts = str(int(time.time() * 1000))
    payload = ts + api_key + _RECV_WINDOW + query
    sign = hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": _RECV_WINDOW,
        "X-BAPI-SIGN": sign,
    }
    url = f"{_BASE}{path}" + (f"?{query}" if query else "")
    try:
        resp = requests.get(url, headers=headers, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise BybitAuthError(f"Сеть недоступна: {exc}") from exc
    if resp.status_code in (401, 403):
        raise BybitAuthError("Неверный API-ключ/секрет или нет прав на чтение (создайте Read-Only ключ)")
    try:
        data = resp.json()
    except ValueError:
        raise BybitAuthError(f"Bybit вернул неожиданный ответ (HTTP {resp.status_code})")
    code = data.get("retCode")
    if code != 0:
        # 10003/10004 — неверный ключ/подпись; 10005 — нет прав.
        raise BybitAuthError(data.get("retMsg") or f"Bybit retCode {code}")
    return data.get("result") or {}


def fetch_wallet_balance(api_key: str, api_secret: str) -> dict[str, Any]:
    """Сводный баланс UNIFIED-аккаунта (общий капитал, доступно, нереал. PnL)."""
    res = _signed_get("/v5/account/wallet-balance", "accountType=UNIFIED", api_key, api_secret)
    lst = res.get("list") or []
    if not lst:
        return {"total_equity": 0.0, "available": 0.0, "unrealized_pnl": 0.0, "coins": []}
    acc = lst[0]
    coins = []
    for c in acc.get("coin", []):
        try:
            eq = float(c.get("equity") or 0)
        except (TypeError, ValueError):
            eq = 0.0
        if eq <= 0:
            continue
        coins.append({
            "coin": c.get("coin"),
            "equity": round(eq, 6),
            "usd_value": round(float(c.get("usdValue") or 0), 2),
        })
    coins.sort(key=lambda x: x["usd_value"], reverse=True)
    return {
        "total_equity": round(float(acc.get("totalEquity") or 0), 2),
        "available": round(float(acc.get("totalAvailableBalance") or 0), 2),
        "unrealized_pnl": round(float(acc.get("totalPerpUPL") or 0), 2),
        "coins": coins[:12],
    }


def fetch_positions(api_key: str, api_secret: str) -> list[dict[str, Any]]:
    """Открытые позиции перпетуалов USDT (read-only)."""
    res = _signed_get("/v5/position/list", "category=linear&settleCoin=USDT", api_key, api_secret)
    out = []
    for p in res.get("list") or []:
        try:
            size = float(p.get("size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size == 0:
            continue
        out.append({
            "symbol": p.get("symbol"),
            "side": (p.get("side") or "").lower(),  # buy/sell
            "size": size,
            "leverage": p.get("leverage"),
            "entry_price": round(float(p.get("avgPrice") or 0), 6),
            "mark_price": round(float(p.get("markPrice") or 0), 6),
            "unrealized_pnl": round(float(p.get("unrealisedPnl") or 0), 4),
            "position_value": round(float(p.get("positionValue") or 0), 2),
        })
    return out
