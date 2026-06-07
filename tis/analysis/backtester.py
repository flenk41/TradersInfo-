# SPDX-License-Identifier: AGPL-3.0-or-later
"""Бэктест торговой стратегии на истории (без реальных сделок).

Упрощённая, но честная модель ядра TIS: трендовый фильтр (EMA20/50) + RSI-полоса
+ стоп по ATR + тейк по R:R + перевод стопа в безубыток после +1R (как в журнале).
Одна позиция за раз; вход по закрытию бара, исход — по касанию high/low следующих
баров (при коллизии в одной свече — консервативно стоп).

НЕ исполняет ордера и не торгует — только статистика «что было бы».
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_WARMUP = 60


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def backtest(
    df: pd.DataFrame,
    rr: float = 2.0,
    atr_mult: float = 2.0,
    breakeven: bool = True,
) -> dict:
    """Прогон стратегии. Возвращает статистику, кривую депозита (в R) и сделки."""
    if df is None or len(df) < _WARMUP + 20:
        return {"available": False, "reason": "not_enough_data"}

    df = df.reset_index(drop=True)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    rsi = _rsi(close)
    atr = _atr(df)

    pos = None  # {side, entry, stop, tp, risk, be, bar}
    trades: list[dict] = []

    def _open(side, i):
        e = float(close.iloc[i])
        a = float(atr.iloc[i])
        if a <= 0:
            return None
        if side == "long":
            stop = e - atr_mult * a
            tp = e + rr * (e - stop)
        else:
            stop = e + atr_mult * a
            tp = e - rr * (stop - e)
        return {"side": side, "entry": e, "stop": stop, "tp": tp, "risk": abs(e - stop),
                "be": False, "bar": i}

    def _check(p, hi, lo):
        if p["side"] == "long":
            if breakeven and not p["be"] and hi >= p["entry"] + p["risk"]:
                p["be"] = True; p["stop"] = p["entry"]
            if lo <= p["stop"]:
                return "be" if p["be"] else "sl"
            if hi >= p["tp"]:
                return "tp"
        else:
            if breakeven and not p["be"] and lo <= p["entry"] - p["risk"]:
                p["be"] = True; p["stop"] = p["entry"]
            if hi >= p["stop"]:
                return "be" if p["be"] else "sl"
            if lo <= p["tp"]:
                return "tp"
        return None

    for i in range(_WARMUP, len(df)):
        if pos is not None:
            res = _check(pos, float(high.iloc[i]), float(low.iloc[i]))
            if res:
                r_mult = rr if res == "tp" else (0.0 if res == "be" else -1.0)
                trades.append({"side": pos["side"], "outcome": res, "r": r_mult,
                               "entry": round(pos["entry"], 6), "bars": i - pos["bar"]})
                pos = None
            continue
        # Флэт — решаем вход по закрытию бара i.
        if np.isnan(rsi.iloc[i]) or np.isnan(ema50.iloc[i]):
            continue
        up = ema20.iloc[i] > ema50.iloc[i]
        r = rsi.iloc[i]
        sep = abs(ema20.iloc[i] - ema50.iloc[i]) / close.iloc[i]  # «сила» тренда
        if sep < 0.002:   # почти флэт — пропускаем (как гейт «не флэт»)
            continue
        if up and 45 <= r <= 68:
            pos = _open("long", i)
        elif (not up) and 32 <= r <= 55:
            pos = _open("short", i)

    return _stats(trades, rr)


def backtest_universe(market: str, region: str = "all", interval: str = "4h",
                      limit: int = 1000, cap: int = 14) -> dict:
    """Бэктест стратегии по набору инструментов — таблица устойчивости.

    Прогоняет backtest() на каждом инструменте вселенной (с потолком) и сводит:
    по инструментам (PF, винрейт, total R, сделки) + агрегат (сколько прибыльных).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tis.data.market_data import fetch_klines
    from tis.data.instruments_catalog import CRYPTO_LIST, FOREX_LIST, STOCKS_RU, STOCKS_US

    if market == "crypto":
        uni = CRYPTO_LIST
    elif market == "forex":
        uni = FOREX_LIST
    elif market == "stock":
        uni = STOCKS_US if region == "us" else STOCKS_RU if region == "ru" else STOCKS_RU + STOCKS_US
    else:
        uni = []
    uni = uni[: max(1, min(cap, 16))]
    if not uni:
        return {"available": False, "rows": []}

    def _one(inst):
        try:
            df = fetch_klines(inst.id, interval=interval, limit=limit, market=market)
            r = backtest(df)
        except Exception:
            return None
        if not r.get("available") or not r.get("trades"):
            return None
        return {
            "id": inst.id, "name": inst.name,
            "trades": r["trades"], "win_rate": r["win_rate"],
            "profit_factor": r["profit_factor"], "total_r": r["total_r"], "avg_r": r["avg_r"],
        }

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_one, inst): inst for inst in uni}
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except Exception:
                r = None
            if r:
                rows.append(r)
    rows.sort(key=lambda x: x["profit_factor"], reverse=True)
    n = len(rows)
    profitable = sum(1 for r in rows if r["profit_factor"] >= 1)
    robust = sum(1 for r in rows if r["profit_factor"] >= 1.3 and r["trades"] >= 20)
    avg_pf = round(sum(r["profit_factor"] for r in rows) / n, 2) if n else 0.0
    total_r = round(sum(r["total_r"] for r in rows), 1)
    return {
        "available": True, "interval": interval, "tested": n,
        "profitable": profitable, "robust": robust, "avg_pf": avg_pf, "total_r": total_r,
        "rows": rows,
    }


def _stats(trades: list[dict], rr: float) -> dict:
    n = len(trades)
    if n == 0:
        return {"available": True, "trades": 0, "reason": "no_trades"}
    wins = [t for t in trades if t["outcome"] == "tp"]
    losses = [t for t in trades if t["outcome"] == "sl"]
    be = [t for t in trades if t["outcome"] == "be"]
    decided = len(wins) + len(losses)
    rs = [t["r"] for t in trades]
    gross_win = sum(r for r in rs if r > 0)
    gross_loss = abs(sum(r for r in rs if r < 0))

    # Кривая депозита в R и максимальная просадка.
    equity, cum, peak, max_dd = [], 0.0, 0.0, 0.0
    for r in rs:
        cum += r
        equity.append(round(cum, 2))
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    longs = [t for t in trades if t["side"] == "long"]
    shorts = [t for t in trades if t["side"] == "short"]

    def _wr(arr):
        d = [t for t in arr if t["outcome"] in ("tp", "sl")]
        w = [t for t in d if t["outcome"] == "tp"]
        return round(len(w) / len(d) * 100, 1) if d else 0.0

    return {
        "available": True,
        "trades": n,
        "wins": len(wins), "losses": len(losses), "breakeven": len(be),
        "win_rate": round(len(wins) / decided * 100, 1) if decided else 0.0,
        "avg_r": round(sum(rs) / n, 2),
        "total_r": round(sum(rs), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (round(gross_win, 2) if gross_win else 0.0),
        "max_drawdown_r": round(max_dd, 2),
        "expectancy_r": round(sum(rs) / n, 2),
        "rr": rr,
        "long_trades": len(longs), "long_wr": _wr(longs),
        "short_trades": len(shorts), "short_wr": _wr(shorts),
        "equity": equity[:400],
    }
