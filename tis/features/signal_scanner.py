# SPDX-License-Identifier: AGPL-3.0-or-later
"""Сканер сигналов: ищет готовые сетапы по нашей стратегии на наборе инструментов.

НЕ торгует — только находит инструменты, где движок даёт направленную
рекомендацию (selective-гейт: сильный балл, по тренду, не флэт), и отдаёт
вход/стоп/тейк/R:R. Пользователь решает и открывает сделку сам.

Использует cached_analysis (тот же кэш, что /api/analyze), поэтому повторные
сканы быстрые. Вселенная ограничивается, чтобы скан был разумным по времени.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from tis.data.instruments_catalog import CRYPTO_LIST, FOREX_LIST, STOCKS_RU, STOCKS_US

_MAX = 14          # потолок инструментов на скан (баланс скорость/покрытие)
_WORKERS = 6


def _universe(market: str, region: str):
    if market == "crypto":
        return CRYPTO_LIST
    if market == "forex":
        return FOREX_LIST
    if market == "stock":
        if region == "us":
            return STOCKS_US
        if region == "ru":
            return STOCKS_RU
        return STOCKS_RU + STOCKS_US
    return []


def _setup_for(inst, market: str) -> dict | None:
    from tis.engine import cached_analysis
    from tis.analysis.position_calculator import PositionInput, calculate_position

    try:
        a = cached_analysis(inst.id, market=market)
    except Exception:
        return None
    rec = a.accuracy.recommended_side if a.accuracy else "wait"
    if rec not in ("long", "short"):
        return None
    try:
        pos = calculate_position(
            a, PositionInput(entry_price=a.price, margin_usdt=100, leverage=10, side=rec)
        )
    except Exception:
        return None
    return {
        "id": inst.id,
        "name": inst.name,
        "subtitle": inst.subtitle or inst.id,
        "market": market,
        "region": getattr(inst, "region", None),
        "side": rec,
        "score": a.accuracy.overall_pct if a.accuracy else None,
        "grade": a.accuracy.confidence_grade if a.accuracy else None,
        "price": round(a.price, 6),
        "entry": pos.entry_price,
        "stop": pos.stop_loss,
        "take_profit": pos.take_profit,
        "rr": pos.risk_reward,
        "trend": a.overall_trend,
    }


def scan_signals(market: str, region: str = "all", limit: int = _MAX) -> dict:
    universe = _universe(market, region)[: max(1, min(limit, _MAX))]
    if not universe:
        return {"available": False, "setups": []}
    setups: list[dict] = []
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futs = {pool.submit(_setup_for, inst, market): inst for inst in universe}
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except Exception:
                r = None
            if r:
                setups.append(r)
    setups.sort(key=lambda x: (x.get("score") or 0), reverse=True)
    return {"available": True, "scanned": len(universe), "setups": setups}
