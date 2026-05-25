"""Журнал сигналов: фиксация и автопроверка исходов (TP/SL) по истории цены.

Идея: вместо эвристической «точности» накапливаем реальные сделки-сигналы и
смотрим, что сработало первым — тейк или стоп. Так получаем измеренный винрейт,
средний R и экспектанси.

Допущения (важно для честности цифр):
- вход считается исполненным сразу по entry в момент сигнала;
- при касании и стопа, и тейка в одной свече консервативно засчитываем СТОП;
- издержки (комиссия/спред) пока не вычитаются — это следующий шаг.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid

_FILE = os.path.join(os.path.dirname(__file__), "signals.json")
_LOCK = threading.Lock()
_EVAL_HORIZON_DAYS = 14
_EVAL_INTERVAL = "1h"
_EVAL_LIMIT = 500


def _load() -> list[dict]:
    if not os.path.exists(_FILE):
        return []
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def _save(rows: list[dict]) -> None:
    tmp = _FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _FILE)


def add_signal(payload: dict) -> dict:
    side = (payload.get("side") or "").lower()
    if side not in ("long", "short"):
        raise ValueError("side должен быть long или short")
    entry = float(payload.get("entry") or 0)
    stop = float(payload.get("stop") or 0)
    tp = float(payload.get("take_profit") or 0)
    if entry <= 0 or stop <= 0 or tp <= 0:
        raise ValueError("Нужны положительные entry, stop и take_profit")
    if side == "long" and not (stop < entry < tp):
        raise ValueError("Для лонга должно быть stop < entry < tp")
    if side == "short" and not (tp < entry < stop):
        raise ValueError("Для шорта должно быть tp < entry < stop")

    risk = abs(entry - stop)
    reward = abs(tp - entry)
    record = {
        "id": uuid.uuid4().hex[:12],
        "created_ts": int(time.time()),
        "pair": payload.get("pair", ""),
        "market": payload.get("market", ""),
        "display": payload.get("display", payload.get("pair", "")),
        "side": side,
        "entry": round(entry, 8),
        "stop": round(stop, 8),
        "take_profit": round(tp, 8),
        "take_profit_2": float(payload["take_profit_2"]) if payload.get("take_profit_2") else None,
        "rr": round(reward / risk, 2) if risk else 0,
        "accuracy_pct": payload.get("accuracy_pct"),
        "status": "open",
        "exit_price": None,
        "outcome_ts": None,
        "r_multiple": None,
        "evaluated_ts": None,
    }
    with _LOCK:
        rows = _load()
        rows.insert(0, record)
        _save(rows)
    return record


def _first_touch(side: str, entry: float, stop: float, tp: float, candles) -> tuple[str, float, int] | None:
    """Возвращает (исход, цена выхода, ts) при первом касании стопа/тейка."""
    for c in candles:
        high = c["high"]
        low = c["low"]
        if side == "long":
            hit_sl = low <= stop
            hit_tp = high >= tp
        else:
            hit_sl = high >= stop
            hit_tp = low <= tp
        if hit_sl and hit_tp:
            return "sl", stop, c["ts"]  # консервативно: стоп первым
        if hit_sl:
            return "sl", stop, c["ts"]
        if hit_tp:
            return "tp", tp, c["ts"]
    return None


def _evaluate(record: dict, fetch_klines) -> bool:
    """Пытается закрыть открытый сигнал. Возвращает True, если статус изменился."""
    if record["status"] != "open":
        return False

    pair = record.get("pair")
    market = record.get("market") or None
    if not pair:
        return False

    try:
        df = fetch_klines(pair, interval=_EVAL_INTERVAL, limit=_EVAL_LIMIT, market=market)
    except Exception:
        return False

    created = record["created_ts"]
    candles = []
    for _, row in df.iterrows():
        ts = int(row["open_time"].timestamp())
        if ts < created:
            continue
        candles.append({"high": float(row["high"]), "low": float(row["low"]), "ts": ts})

    side = record["side"]
    entry = record["entry"]
    stop = record["stop"]
    tp = record["take_profit"]
    risk = abs(entry - stop) or 1e-9

    touch = _first_touch(side, entry, stop, tp, candles)
    now = int(time.time())
    if touch:
        outcome, exit_price, ts = touch
        record["status"] = outcome
        record["exit_price"] = round(exit_price, 8)
        record["outcome_ts"] = ts
        record["r_multiple"] = round((abs(tp - entry) / risk) if outcome == "tp" else -1.0, 2)
        record["evaluated_ts"] = now
        return True

    if now - created > _EVAL_HORIZON_DAYS * 86400:
        record["status"] = "expired"
        record["evaluated_ts"] = now
        return True

    record["evaluated_ts"] = now
    return False


def evaluate_open(fetch_klines) -> int:
    """Прогоняет все открытые сигналы. Возвращает число закрытых за вызов."""
    with _LOCK:
        rows = _load()
        changed = 0
        for r in rows:
            if r["status"] == "open" and _evaluate(r, fetch_klines):
                changed += 1
        if changed:
            _save(rows)
        return changed


def _stats(rows: list[dict]) -> dict:
    closed = [r for r in rows if r["status"] in ("tp", "sl")]
    wins = [r for r in closed if r["status"] == "tp"]
    losses = [r for r in closed if r["status"] == "sl"]
    n = len(closed)
    rs = [r["r_multiple"] for r in closed if r.get("r_multiple") is not None]
    gross_win = sum(r for r in rs if r > 0)
    gross_loss = abs(sum(r for r in rs if r < 0))
    return {
        "total": len(rows),
        "open": sum(1 for r in rows if r["status"] == "open"),
        "closed": n,
        "wins": len(wins),
        "losses": len(losses),
        "expired": sum(1 for r in rows if r["status"] == "expired"),
        "win_rate": round(len(wins) / n * 100, 1) if n else 0.0,
        "avg_r": round(sum(rs) / len(rs), 2) if rs else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (round(gross_win, 2) if gross_win else 0.0),
    }


def get_journal(fetch_klines=None) -> dict:
    if fetch_klines is not None:
        evaluate_open(fetch_klines)
    with _LOCK:
        rows = _load()
    return {"signals": rows, "stats": _stats(rows)}


def delete_signal(signal_id: str) -> bool:
    with _LOCK:
        rows = _load()
        new = [r for r in rows if r["id"] != signal_id]
        if len(new) == len(rows):
            return False
        _save(new)
        return True


def clear_all() -> None:
    with _LOCK:
        _save([])
