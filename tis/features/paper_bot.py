# SPDX-License-Identifier: AGPL-3.0-or-later
"""Серверный БУМАЖНЫЙ бот: торгует виртуально по стратегии TIS 24/7.

Без ключей и реальных денег — демонстрация эффективности стратегии вживую.
Одна общая инстанция (демо), состояние в памяти + файл (переживает рестарт).
Тикает в фоне: на наборе инструментов открывает/ведёт виртуальные позиции
(одна на инструмент), стоп/тейк по ATR/R:R, безубыток после +1R. Считает
винрейт, средний R, профит-фактор и кривую депозита в R.
"""

from __future__ import annotations

import json
import os
import threading
import time

_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LINKUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "ATOMUSDT", "LTCUSDT"]
_INTERVAL = "1h"
_TICK_SEC = 120
_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "paper_bot.json")

_lock = threading.Lock()
_started = False
_state = {
    "started_ts": None,
    "last_tick": None,
    "positions": {},   # symbol -> {side, entry, stop, tp, risk, be, opened_ts}
    "closed": [],      # последние сделки {symbol, side, outcome, r, entry, exit, ts}
    "equity": [],      # кумулятивная R
}


def _load():
    global _state
    try:
        if os.path.exists(_STATE_FILE):
            with open(_STATE_FILE, encoding="utf-8") as f:
                _state = json.load(f)
    except Exception:
        pass


def _save():
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(_state, f)
    except Exception:
        pass


def _tick():
    from tis.data.market_data import fetch_klines
    from tis.analysis.backtester import signal_now

    now = int(time.time())
    for sym in _SYMBOLS:
        try:
            df = fetch_klines(sym, interval=_INTERVAL, limit=400, market="crypto")
        except Exception:
            continue
        if df is None or len(df) < 220:
            continue
        last = df.iloc[-1]
        hi, lo = float(last["high"]), float(last["low"])
        pos = _state["positions"].get(sym)
        if pos:
            _manage(sym, pos, hi, lo, now)
        else:
            sig = signal_now(df, use_ema200=True)
            if sig:
                _state["positions"][sym] = {
                    "side": sig["side"], "entry": sig["entry"], "stop": sig["stop"],
                    "tp": sig["tp"], "risk": abs(sig["entry"] - sig["stop"]),
                    "be": False, "opened_ts": now,
                }
    _state["last_tick"] = now
    _save()


def _manage(sym, p, hi, lo, now):
    side, entry, risk = p["side"], p["entry"], p["risk"] or 1e-9
    outcome = None
    if side == "long":
        if not p["be"] and hi >= entry + risk:
            p["be"] = True; p["stop"] = entry
        if lo <= p["stop"]:
            outcome = "be" if p["be"] else "sl"; exitp = p["stop"]
        elif hi >= p["tp"]:
            outcome = "tp"; exitp = p["tp"]
    else:
        if not p["be"] and lo <= entry - risk:
            p["be"] = True; p["stop"] = entry
        if hi >= p["stop"]:
            outcome = "be" if p["be"] else "sl"; exitp = p["stop"]
        elif lo <= p["tp"]:
            outcome = "tp"; exitp = p["tp"]
    if outcome:
        r = round(abs(p["tp"] - entry) / risk, 2) if outcome == "tp" else (0.0 if outcome == "be" else -1.0)
        _state["closed"].insert(0, {
            "symbol": sym, "side": side, "outcome": outcome, "r": r,
            "entry": entry, "exit": round(exitp, 6), "ts": now,
        })
        _state["closed"] = _state["closed"][:50]
        cum = (_state["equity"][-1] if _state["equity"] else 0.0) + r
        _state["equity"].append(round(cum, 2))
        _state["equity"] = _state["equity"][-300:]
        del _state["positions"][sym]


def _loop():
    while True:
        try:
            with _lock:
                _tick()
        except Exception:
            pass
        time.sleep(_TICK_SEC)


def ensure_running():
    """Лениво запускает фоновый поток один раз."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
        _load()
        if not _state.get("started_ts"):
            _state["started_ts"] = int(time.time())
    threading.Thread(target=_loop, daemon=True).start()


def get_state() -> dict:
    with _lock:
        closed = [r for r in _state["closed"] if r["outcome"] in ("tp", "sl", "be")]
        wins = [r for r in closed if r["outcome"] == "tp"]
        losses = [r for r in closed if r["outcome"] == "sl"]
        decided = len(wins) + len(losses)
        rs = [r["r"] for r in closed]
        gw = sum(r for r in rs if r > 0)
        gl = abs(sum(r for r in rs if r < 0))
        return {
            "started_ts": _state.get("started_ts"),
            "last_tick": _state.get("last_tick"),
            "symbols": _SYMBOLS,
            "interval": _INTERVAL,
            "open_positions": [
                {"symbol": s, **p} for s, p in _state["positions"].items()
            ],
            "recent": _state["closed"][:15],
            "equity": _state["equity"],
            "stats": {
                "closed": len(closed),
                "wins": len(wins), "losses": len(losses),
                "breakeven": sum(1 for r in closed if r["outcome"] == "be"),
                "win_rate": round(len(wins) / decided * 100, 1) if decided else 0.0,
                "total_r": round(sum(rs), 2),
                "avg_r": round(sum(rs) / len(rs), 2) if rs else 0.0,
                "profit_factor": round(gw / gl, 2) if gl else (round(gw, 2) if gw else 0.0),
            },
        }
