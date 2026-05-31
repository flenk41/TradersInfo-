"""Риск-метрики портфеля по дневной истории: доходность, волатильность,
Sharpe, макс. просадка + кривая капитала.

Портфель и список наблюдения хранятся у пользователя в браузере (localStorage),
сюда приходят только позиции для расчёта. Значения считаются в номинале (без
конвертации валют) — для однотонного по валюте портфеля это корректно; при
смешении валют это приближение (показываем дисклеймер на фронте).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_data import fetch_klines

_DAYS = 190
_TRADING = 252


def _series(pair: str, market: str | None) -> pd.Series:
    df = fetch_klines(pair, interval="1d", limit=_DAYS, market=market)
    s = df.set_index(df["open_time"].dt.normalize())["close"].astype(float)
    return s[~s.index.duplicated(keep="last")]


def _empty() -> dict:
    return {
        "ok_holdings": 0, "value": 0.0, "cost": 0.0, "pnl": 0.0, "pnl_pct": 0.0,
        "total_return_pct": 0.0, "volatility_pct": 0.0, "sharpe": 0.0, "max_drawdown_pct": 0.0,
        "equity": [], "holdings": [],
    }


def portfolio_risk(holdings: list[dict]) -> dict:
    series: dict[str, pd.Series] = {}
    valid: list[dict] = []
    for h in holdings or []:
        pair = (h.get("pair") or "").strip()
        if not pair:
            continue
        try:
            qty = float(h.get("qty") or 0)
            entry = float(h.get("entry") or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        market = (h.get("market") or "").strip().lower() or None
        try:
            s = _series(pair, market)
        except Exception:
            continue
        if len(s) < 20:
            continue
        series[pair] = s
        valid.append({"pair": pair, "market": market, "qty": qty, "entry": entry,
                      "name": h.get("name") or pair})

    if not valid:
        return _empty()

    df = pd.DataFrame(series).dropna()
    if len(df) < 20:
        # нет общего пересечения дат — считаем хотя бы текущие значения
        df = pd.DataFrame(series).ffill().dropna()
    qty_map = {h["pair"]: h["qty"] for h in valid}

    port = sum(df[p] * qty_map[p] for p in df.columns)
    returns = port.pct_change().dropna()

    total_return = (port.iloc[-1] / port.iloc[0] - 1) * 100 if port.iloc[0] else 0.0
    vol = float(returns.std() * np.sqrt(_TRADING) * 100) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / returns.std() * np.sqrt(_TRADING)) if returns.std() else 0.0
    running_max = port.cummax()
    drawdown = (port / running_max - 1) * 100
    max_dd = float(drawdown.min()) if len(drawdown) else 0.0

    value = float(sum(df[p].iloc[-1] * qty_map[p] for p in df.columns))
    cost = float(sum(h["entry"] * h["qty"] for h in valid if h["entry"] > 0))
    pnl = value - cost if cost else 0.0
    pnl_pct = (pnl / cost * 100) if cost else 0.0

    # кривая капитала — прорежаем до ~60 точек
    eq = port.tolist()
    step = max(1, len(eq) // 60)
    equity = [round(float(v), 2) for v in eq[::step]]

    out_holdings = []
    for h in valid:
        cur = float(df[h["pair"]].iloc[-1])
        v = cur * h["qty"]
        hp = (cur - h["entry"]) / h["entry"] * 100 if h["entry"] > 0 else None
        out_holdings.append({
            "pair": h["pair"], "name": h["name"], "market": h["market"],
            "qty": h["qty"], "entry": h["entry"], "price": round(cur, 6),
            "value": round(v, 2), "pnl_pct": round(hp, 2) if hp is not None else None,
            "weight_pct": round(v / value * 100, 1) if value else 0.0,
        })

    return {
        "ok_holdings": len(valid),
        "value": round(value, 2),
        "cost": round(cost, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "total_return_pct": round(total_return, 2),
        "volatility_pct": round(vol, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "equity": equity,
        "holdings": out_holdings,
    }
