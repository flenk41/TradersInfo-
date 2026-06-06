"""Журнал сигналов — STATELESS оценка исходов (TP/SL) по истории цены.

⚠️ Сервер НЕ хранит журнал. Записи живут на КЛИЕНТЕ (localStorage, как watchlist
и портфель) — поэтому нет общего файла, нет «утечки» данных между пользователями
и нет гонок на запись. Под мобильные приложения это родная модель.

Здесь только чистые функции:
- `build_record(payload)` — валидирует форму и собирает запись (id, R:R, статус open);
- `evaluate(signals, fetch_klines)` — по истории цены смотрит, что сработало
  первым (тейк/стоп), закрывает открытые записи и считает статистику.

Допущения (для честности цифр):
- вход исполнен сразу по entry в момент сигнала;
- если в одной свече задеты и стоп, и тейк — консервативно засчитываем СТОП;
- издержки (комиссия/спред) пока не вычитаются.
"""

from __future__ import annotations

import time
import uuid

_EVAL_HORIZON_DAYS = 14
_EVAL_INTERVAL = "1h"
_EVAL_LIMIT = 500


def build_record(payload: dict) -> dict:
    """Валидирует форму и возвращает готовую запись журнала (без сохранения)."""
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
    return {
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


def _first_touch(side: str, entry: float, stop: float, tp: float, candles) -> tuple[str, float, int] | None:
    """Первое касание стопа/тейка с переводом стопа в безубыток после +1R.

    Реалистичное управление позицией: как только цена прошла +1R в нашу сторону
    (на расстояние риска), стоп переносится в безубыток (на вход). Дальше:
      • дошли до тейка → "tp";
      • откатились к входу (после +1R) → "be" (0R, не убыток);
      • выбило исходным стопом до +1R → "sl" (−1R).
    Коллизия в одной свече — консервативно (ближний уровень первым).
    """
    risk = abs(entry - stop)
    moved_be = False        # стоп уже в безубытке?
    cur_stop = stop
    for c in candles:
        high, low, ts = c["high"], c["low"], c["ts"]
        # 1) фиксируем достижение +1R (перевод стопа в БУ на этой же свече)
        reached_1r = (high >= entry + risk) if side == "long" else (low <= entry - risk)
        if not moved_be and reached_1r:
            moved_be = True
            cur_stop = entry
        # 2) касания относительно текущего стопа
        if side == "long":
            hit_sl = low <= cur_stop
            hit_tp = high >= tp
        else:
            hit_sl = high >= cur_stop
            hit_tp = low <= tp
        if hit_sl and hit_tp:
            # ближний уровень первым: стоп ближе входа, чем тейк (R:R≥1)
            return ("be" if moved_be else "sl"), cur_stop, ts
        if hit_sl:
            return ("be" if moved_be else "sl"), cur_stop, ts
        if hit_tp:
            return "tp", tp, ts
    return None


def _evaluate(record: dict, fetch_klines) -> bool:
    """Пытается закрыть открытый сигнал. Возвращает True, если статус изменился."""
    if record.get("status") != "open":
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

    # Защита от рассинхрона пары и уровней: если entry несопоставим с ценами
    # инструмента (напр. уровни BTC ~$71k записаны для INJ ~$1.9), любое касание
    # тейка/стопа было бы ложным — не закрываем такую битую запись.
    if candles:
        lo = min(c["low"] for c in candles)
        hi = max(c["high"] for c in candles)
        if hi > 0 and lo > 0 and (entry > hi * 5 or entry < lo / 5):
            record["evaluated_ts"] = int(time.time())
            return False

    touch = _first_touch(side, entry, stop, tp, candles)
    now = int(time.time())
    if touch:
        outcome, exit_price, ts = touch
        record["status"] = outcome
        record["exit_price"] = round(exit_price, 8)
        record["outcome_ts"] = ts
        # tp: +R:R; sl: −1R; be (безубыток после +1R): 0R.
        if outcome == "tp":
            r_mult = round(abs(tp - entry) / risk, 2)
        elif outcome == "be":
            r_mult = 0.0
        else:
            r_mult = -1.0
        record["r_multiple"] = r_mult
        record["evaluated_ts"] = now
        return True

    if now - created > _EVAL_HORIZON_DAYS * 86400:
        record["status"] = "expired"
        record["evaluated_ts"] = now
        return True

    record["evaluated_ts"] = now
    return False


def _stats(rows: list[dict]) -> dict:
    closed = [r for r in rows if r.get("status") in ("tp", "sl", "be")]
    wins = [r for r in closed if r["status"] == "tp"]
    losses = [r for r in closed if r["status"] == "sl"]
    breakeven = [r for r in closed if r["status"] == "be"]
    decided = len(wins) + len(losses)  # винрейт считаем без безубытков
    rs = [r["r_multiple"] for r in closed if r.get("r_multiple") is not None]
    gross_win = sum(r for r in rs if r > 0)
    gross_loss = abs(sum(r for r in rs if r < 0))
    return {
        "total": len(rows),
        "open": sum(1 for r in rows if r.get("status") == "open"),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "expired": sum(1 for r in rows if r.get("status") == "expired"),
        "win_rate": round(len(wins) / decided * 100, 1) if decided else 0.0,
        "avg_r": round(sum(rs) / len(rs), 2) if rs else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (round(gross_win, 2) if gross_win else 0.0),
    }


def evaluate(signals: list[dict], fetch_klines) -> dict:
    """Stateless: оценивает открытые записи (история цены) и считает статистику.

    Принимает список записей (с клиента), возвращает обновлённый список + stats.
    Ничего не хранит на сервере."""
    rows = [dict(s) for s in (signals or [])]
    for r in rows:
        if r.get("status") == "open":
            try:
                _evaluate(r, fetch_klines)
            except Exception:
                pass
    return {"signals": rows, "stats": _stats(rows)}
