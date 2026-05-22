"""Инструменты для скальпинга (5m / 15m)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ScalpSignal:
    timeframe: str
    direction: str
    entry_zone: str
    stop_hint: str
    target_hint: str
    score: int
    note: str


@dataclass
class ScalpingAnalysis:
    verdict: str
    best_side: str
    scalp_score: int
    signals: list[ScalpSignal] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)
    vwap: float | None = None
    price_vs_vwap: str = ""


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _vwap(df: pd.DataFrame) -> float:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, np.nan)
    cum = (tp * vol).cumsum() / vol.cumsum()
    return float(cum.iloc[-1]) if not np.isnan(cum.iloc[-1]) else float(df["close"].iloc[-1])


def _rsi(close: pd.Series, period: int = 7) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    v = 100 - (100 / (1 + rs))
    return float(v.iloc[-1]) if not np.isnan(v.iloc[-1]) else 50.0


def analyze_scalp_tf(df: pd.DataFrame, timeframe: str, price: float, atr: float) -> ScalpSignal | None:
    if len(df) < 30:
        return None

    close = df["close"]
    vwap = _vwap(df.tail(50))
    ema9 = float(_ema(close, 9).iloc[-1])
    ema21 = float(_ema(close, 21).iloc[-1])
    rsi = _rsi(close, 7)
    vol = df["volume"]
    vol_spike = float(vol.iloc[-1]) > float(vol.tail(20).mean()) * 1.4

    score = 0
    direction = "neutral"
    notes: list[str] = []

    if price > vwap and ema9 > ema21:
        direction = "long"
        score += 3
        notes.append("выше VWAP, EMA9>21")
    elif price < vwap and ema9 < ema21:
        direction = "short"
        score += 3
        notes.append("ниже VWAP, EMA9<21")

    if 40 <= rsi <= 55 and direction == "long":
        score += 2
    elif 45 <= rsi <= 60 and direction == "short":
        score += 2
    if vol_spike:
        score += 2
        notes.append("всплеск объёма")

    if direction == "long":
        entry_low = min(vwap, ema9) * 0.9995
        entry_high = price * 1.0005
        stop = entry_low - atr * 0.5
        target = price + atr * 1.2
        return ScalpSignal(
            timeframe=timeframe,
            direction="long",
            entry_zone=f"${entry_low:,.4f} – ${entry_high:,.4f}",
            stop_hint=f"Стоп ${stop:,.4f} (~{((price-stop)/price*100):.2f}%)",
            target_hint=f"Цель ${target:,.4f}",
            score=min(100, score * 12),
            note=", ".join(notes),
        )
    if direction == "short":
        entry_low = price * 0.9995
        entry_high = max(vwap, ema9) * 1.0005
        stop = entry_high + atr * 0.5
        target = price - atr * 1.2
        return ScalpSignal(
            timeframe=timeframe,
            direction="short",
            entry_zone=f"${entry_low:,.4f} – ${entry_high:,.4f}",
            stop_hint=f"Стоп ${stop:,.4f}",
            target_hint=f"Цель ${target:,.4f}",
            score=min(100, score * 12),
            note=", ".join(notes),
        )
    return None


def build_scalping_analysis(
    klines_5m: pd.DataFrame | None,
    klines_15m: pd.DataFrame | None,
    price: float,
    atr: float,
) -> ScalpingAnalysis:
    signals: list[ScalpSignal] = []
    tips = [
        "Скальп: риск 0.3–0.8% на сделку, плечо минимальное",
        "Лучшие часы — пересечение сессий (Лондон / NY)",
        "Не скальпируйте во флэте (ADX < 18 на 15m)",
    ]

    vwap_val = None
    price_vs_vwap = ""
    if klines_5m is not None and len(klines_5m) > 20:
        vwap_val = _vwap(klines_5m.tail(80))
        diff = (price - vwap_val) / vwap_val * 100
        price_vs_vwap = f"Цена {'выше' if diff > 0 else 'ниже'} VWAP на {abs(diff):.2f}%"

    for tf, df in [("5m", klines_5m), ("15m", klines_15m)]:
        if df is not None:
            sig = analyze_scalp_tf(df, tf, price, atr)
            if sig:
                signals.append(sig)

    long_score = sum(s.score for s in signals if s.direction == "long")
    short_score = sum(s.score for s in signals if s.direction == "short")

    if long_score > short_score + 15:
        best_side = "long"
        verdict = "Скальп: приоритет ЛОНГ 🟢"
    elif short_score > long_score + 15:
        best_side = "short"
        verdict = "Скальп: приоритет ШОРТ 🔴"
    else:
        best_side = "wait"
        verdict = "Скальп: ждите — нет чёткого направления"

    return ScalpingAnalysis(
        verdict=verdict,
        best_side=best_side,
        scalp_score=max(long_score, short_score),
        signals=signals,
        tips=tips,
        vwap=round(vwap_val, 6) if vwap_val else None,
        price_vs_vwap=price_vs_vwap,
    )
