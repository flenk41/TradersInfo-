# SPDX-License-Identifier: AGPL-3.0-or-later
"""Smart Money Concepts (SMC/ICT): снятие ликвидности, ордер-блоки, слом
структуры (BOS/CHoCH) и зоны premium/discount.

Детерминированно, без сети — усиливает анализ и балл согласованности так же,
как это делает ИИ-агент в TradingView: ищет, где «умные деньги» собирают
ликвидность и откуда вероятен импульс.

Термины:
- Liquidity sweep — снятие ликвидности: цена прокалывает прошлый свинг
  (там стоят стопы) и возвращается обратно → стоп-хант, разворот в обратную сторону.
- Order block (OB) — последняя противоположная свеча перед сильным импульсом;
  зона, откуда «умные деньги» заходили (часто ретестится).
- BOS (break of structure) — пробой структуры в сторону тренда (продолжение).
- CHoCH (change of character) — слом структуры против тренда (возможен разворот).
- Premium/Discount — верхняя/нижняя половина диапазона: лонги выгоднее в discount,
  шорты — в premium (равновесие ~50%).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _swing_points(df: pd.DataFrame, window: int = 3) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Свинговые максимумы/минимумы как (индекс, цена)."""
    highs = df["high"].astype(float).values
    lows = df["low"].astype(float).values
    n = len(highs)
    sh: list[tuple[int, float]] = []
    sl: list[tuple[int, float]] = []
    for i in range(window, n - window):
        seg_h = highs[i - window : i + window + 1]
        seg_l = lows[i - window : i + window + 1]
        if highs[i] == seg_h.max():
            sh.append((i, float(highs[i])))
        if lows[i] == seg_l.min():
            sl.append((i, float(lows[i])))
    return sh, sl


def _premium_discount(df: pd.DataFrame, price: float) -> dict | None:
    hi = float(df["high"].max())
    lo = float(df["low"].min())
    if hi <= lo:
        return None
    pct = max(0.0, min(1.0, (price - lo) / (hi - lo)))
    if pct >= 0.66:
        zone, hint = "premium", "Цена в premium — выгоднее искать шорты"
    elif pct <= 0.34:
        zone, hint = "discount", "Цена в discount — выгоднее искать лонги"
    else:
        zone, hint = "equilibrium", "Цена у равновесия (~50%) — без перевеса"
    return {
        "pct": round(pct, 3),
        "zone": zone,
        "range_low": round(lo, 6),
        "range_high": round(hi, 6),
        "eq": round((hi + lo) / 2, 6),
        "hint": hint,
    }


def _liquidity_sweeps(df: pd.DataFrame, window: int = 3, recent: int = 6) -> list[dict]:
    """Снятие ликвидности: недавний бар прокалывает прошлый свинг и закрывается обратно."""
    d = df.reset_index(drop=True)
    n = len(d)
    if n < window * 2 + recent + 2:
        return []
    highs = d["high"].astype(float).values
    lows = d["low"].astype(float).values
    closes = d["close"].astype(float).values
    sh, sl = _swing_points(d, window)
    cut = n - recent
    prior_highs = [p for (i, p) in sh if i < cut]
    prior_lows = [p for (i, p) in sl if i < cut]
    sweeps: list[dict] = []

    if prior_lows:
        pool = prior_lows[-1]  # ближайший прошлый свинг-минимум (там сидят sell-side стопы)
        if any(lows[j] < pool and closes[j] > pool for j in range(cut, n)):
            sweeps.append({
                "side": "bullish",
                "level": round(pool, 6),
                "label": "Снятие ликвидности снизу (стоп-хант) → отскок вверх",
            })
    if prior_highs:
        pool = prior_highs[-1]
        if any(highs[j] > pool and closes[j] < pool for j in range(cut, n)):
            sweeps.append({
                "side": "bearish",
                "level": round(pool, 6),
                "label": "Снятие ликвидности сверху (стоп-хант) → откат вниз",
            })
    return sweeps


def _order_blocks(df: pd.DataFrame, price: float, body_mult: float = 1.5, max_each: int = 1) -> list[dict]:
    """Ордер-блоки: последняя противоположная свеча перед сильным импульсом."""
    d = df.reset_index(drop=True)
    o = d["open"].astype(float).values
    h = d["high"].astype(float).values
    low = d["low"].astype(float).values
    c = d["close"].astype(float).values
    n = len(d)
    if n < 6:
        return []
    bodies = np.abs(c - o)
    avg_body = float(bodies.mean()) or 1e-9

    bull: list[dict] = []
    bear: list[dict] = []
    for i in range(2, n - 1):
        # бычий импульс → ищем последнюю медвежью свечу перед ним = бычий OB
        if (c[i] - o[i]) > body_mult * avg_body:
            for k in range(i - 1, max(-1, i - 5), -1):
                if c[k] < o[k]:
                    lo_e, hi_e = float(low[k]), float(h[k])
                    # неотработанный (цена ещё не прошла насквозь после)
                    mitigated = any(low[j] <= lo_e and h[j] >= hi_e for j in range(i + 1, n))
                    if not mitigated:
                        bull.append({"kind": "bullish", "low": round(lo_e, 6), "high": round(hi_e, 6), "idx": k})
                    break
        if (o[i] - c[i]) > body_mult * avg_body:
            for k in range(i - 1, max(-1, i - 5), -1):
                if c[k] > o[k]:
                    lo_e, hi_e = float(low[k]), float(h[k])
                    mitigated = any(low[j] <= lo_e and h[j] >= hi_e for j in range(i + 1, n))
                    if not mitigated:
                        bear.append({"kind": "bearish", "low": round(lo_e, 6), "high": round(hi_e, 6), "idx": k})
                    break

    out: list[dict] = []
    # ближайший бычий OB ниже цены и ближайший медвежий OB выше цены — самые торгуемые
    bull_below = [b for b in bull if (b["low"] + b["high"]) / 2 <= price]
    bear_above = [b for b in bear if (b["low"] + b["high"]) / 2 >= price]
    for src in (bull_below[-max_each:], bear_above[-max_each:]):
        for b in src:
            mid = (b["low"] + b["high"]) / 2
            out.append({
                "kind": b["kind"],
                "low": b["low"],
                "high": b["high"],
                "mid": round(mid, 6),
                "price": round(mid, 6),
                "distance_pct": round((mid - price) / price * 100, 2),
                "label": "Бычий ордер-блок" if b["kind"] == "bullish" else "Медвежий ордер-блок",
            })
    return out


def _bos_choch(df: pd.DataFrame, window: int = 3) -> dict:
    sh, sl = _swing_points(df, window)
    if len(sh) < 2 or len(sl) < 2:
        return {"event": "none", "direction": "neutral", "detail": "Мало свингов для структуры"}
    close = float(df["close"].iloc[-1])
    last_sh, prev_sh = sh[-1][1], sh[-2][1]
    last_sl, prev_sl = sl[-1][1], sl[-2][1]
    uptrend = last_sh > prev_sh and last_sl > prev_sl
    downtrend = last_sh < prev_sh and last_sl < prev_sl

    if close > last_sh:
        if downtrend:
            return {"event": "CHoCH", "direction": "long", "detail": "Слом нисходящей структуры вверх (CHoCH) — возможен разворот"}
        return {"event": "BOS", "direction": "long", "detail": "Пробой структуры вверх (BOS) — продолжение"}
    if close < last_sl:
        if uptrend:
            return {"event": "CHoCH", "direction": "short", "detail": "Слом восходящей структуры вниз (CHoCH) — возможен разворот"}
        return {"event": "BOS", "direction": "short", "detail": "Пробой структуры вниз (BOS) — продолжение"}
    return {"event": "none", "direction": "neutral", "detail": "Цена внутри текущей структуры"}


def analyze_smc(df: pd.DataFrame, price: float, lookback: int = 120) -> dict | None:
    """Сводный SMC-разбор. Возвращает сигналы + направленный smc_bias + текст."""
    if df is None or len(df) < 20 or not price or price <= 0:
        return None
    d = df.tail(lookback).reset_index(drop=True)

    pd_zone = _premium_discount(d, price)
    sweeps = _liquidity_sweeps(d)
    obs = _order_blocks(d, price)
    bos = _bos_choch(d)

    votes = 0
    if pd_zone:
        votes += 1 if pd_zone["zone"] == "discount" else -1 if pd_zone["zone"] == "premium" else 0
    for s in sweeps:
        votes += 1 if s["side"] == "bullish" else -1
    if bos["direction"] == "long":
        votes += 1
    elif bos["direction"] == "short":
        votes -= 1

    bias = "long" if votes >= 2 else "short" if votes <= -2 else "neutral"

    parts: list[str] = []
    if bos["event"] != "none":
        parts.append(bos["detail"])
    for s in sweeps:
        parts.append(s["label"])
    if pd_zone:
        parts.append(pd_zone["hint"])
    summary = " · ".join(parts) if parts else "Явных SMC-сигналов рядом нет"

    return {
        "smc_bias": bias,
        "votes": votes,
        "premium_discount": pd_zone,
        "liquidity_sweeps": sweeps,
        "order_blocks": obs,
        "bos_choch": bos,
        "summary": summary,
    }
