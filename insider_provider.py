# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 flenk41 (Trading Info Stats). Dual-licensed: AGPL-3.0 or a
# commercial license (see COMMERCIAL.md).
"""Инсайдерский / «умные деньги» фактор для акций.

- **US-акции:** живой сигнал по SEC Form 4 (EDGAR, без ключа). Покупки инсайдеров —
  особенно топ-менеджмента, крупные и кластерные — статистически бычьи (см.
  insider_backtest.py: win 21д у покупок CEO/CFO/директоров и крупных ≈ 94–100%).
- **РФ-акции:** Form 4 не существует. Берём доступный прокси «умных денег» —
  доли инсайдеров/институционалов (yfinance .info). Это слабее транзакций, поэтому
  и вклад в балл меньше.
- **Крипта/валюта:** N/A (нет регуляторного раскрытия) → {"available": False}.

Возвращает dict для `MarketAnalysis.insider`. Поле `score_adj` (−6..+8) аккуратно
прибавляется к баллу согласованности в accuracy_estimator (как новостной фон).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from data_cache import get_cached

_EXEC_KEYS = ("CEO", "CFO", "PRESIDENT", "CHIEF", "COO")


def _ticker_to_cik(ticker: str) -> str | None:
    """ticker → CIK10 по SEC company_tickers.json (кэш 24ч)."""
    from insider_backtest import TICKERS_URL, _get

    raw = get_cached("sec:company_tickers", lambda: json.loads(_get(TICKERS_URL)), ttl=86400)
    t = ticker.upper()
    for r in raw.values():
        if r.get("ticker", "").upper() == t:
            return str(r["cik_str"]).zfill(10)
    return None


def _classify(trades: list, ticker: str) -> dict:
    """Из сырых сделок → бычий/медвежий сигнал + вклад в балл."""
    from insider_backtest import _cluster_buys

    buys = [t for t in trades if t.action == "BUY"]
    sells = [t for t in trades if t.action == "SELL"]
    buy_val = sum(t.value for t in buys)
    sell_val = sum(t.value for t in sells)
    exec_buys = [t for t in buys if any(k in t.role.upper() for k in _EXEC_KEYS)]
    big_buys = [t for t in buys if t.value > 250_000]
    cluster = _cluster_buys(buys, window_days=14, min_insiders=2)
    n_buyers = len({t.insider for t in buys})

    bias = "neutral"
    adj = 0
    notes: list[str] = []

    if exec_buys or len(big_buys) >= 1 or cluster:
        bias = "bullish"
        adj = 8 if (exec_buys and (cluster or big_buys)) else 6
        if exec_buys:
            notes.append(f"Покупки топ-менеджмента ({len(exec_buys)})")
        if cluster:
            notes.append(f"Кластер покупок ({n_buyers} инсайдера)")
        if big_buys:
            notes.append(f"Крупные покупки >$250k ({len(big_buys)})")
    elif buy_val > sell_val * 1.2 and buys:
        bias = "bullish"
        adj = 3
        notes.append("Чистая покупка инсайдерами")
    elif sell_val > buy_val * 3 and len(sells) >= 3:
        # Продажи — слабый сигнал (часто плановые), поэтому лёгкий минус.
        bias = "bearish"
        adj = -3
        notes.append("Преобладают продажи инсайдеров")
    else:
        notes.append("Нет выраженного инсайдерского сигнала")

    return {
        "available": True,
        "kind": "us_insider",
        "bias": bias,
        "score_adj": adj,
        "label": "Покупки инсайдеров" if bias == "bullish" else ("Продажи инсайдеров" if bias == "bearish" else "Инсайдеры нейтральны"),
        "summary": "; ".join(notes),
        "buys": len(buys),
        "sells": len(sells),
        "buy_value": round(buy_val),
        "sell_value": round(sell_val),
        "window_days": 90,
        "recent": [
            {
                "date": t.txn_date,
                "insider": t.insider[:40],
                "role": t.role,
                "action": t.action,
                "value": round(t.value),
            }
            for t in sorted(trades, key=lambda x: x.txn_date, reverse=True)[:6]
        ],
    }


def _us_insider(ticker: str, days: int = 90, max_filings: int = 30) -> dict | None:
    from insider_backtest import ARCHIVE, _get, list_form4, parse_form4

    cik10 = _ticker_to_cik(ticker)
    if not cik10:
        return None
    since = datetime.now(timezone.utc) - timedelta(days=days)
    filings = list_form4(cik10, since)[:max_filings]
    cik = str(int(cik10))
    trades: list = []
    for fl in filings:
        doc = (fl.get("doc") or "").split("/")[-1]
        if not doc.lower().endswith(".xml"):
            continue
        url = ARCHIVE.format(cik=cik, acc_nodash=fl["accession"].replace("-", ""), doc=doc)
        try:
            trades.extend(parse_form4(_get(url), fl, ticker))
        except Exception:
            continue
    if not trades:
        return {"available": True, "kind": "us_insider", "bias": "neutral", "score_adj": 0,
                "label": "Инсайдеры: нет сделок за 90д", "summary": "За 90 дней не было рыночных покупок/продаж (P/S).",
                "buys": 0, "sells": 0, "buy_value": 0, "sell_value": 0, "window_days": days, "recent": []}
    return _classify(trades, ticker)


def _ru_ownership(yf_symbol: str) -> dict | None:
    """РФ-прокси «умных денег»: доли инсайдеров/институционалов (yfinance .info)."""
    try:
        import yfinance as yf

        info = yf.Ticker(yf_symbol).info or {}
    except Exception:
        return None
    insiders = info.get("heldPercentInsiders")
    insts = info.get("heldPercentInstitutions")
    if insiders is None and insts is None:
        return {"available": False}
    ins_pct = round((insiders or 0) * 100, 1)
    inst_pct = round((insts or 0) * 100, 1)
    bias = "neutral"
    adj = 0
    notes = []
    # Высокая доля инсайдеров = «skin in the game»; высокая институциональная = доверие.
    if ins_pct >= 10:
        adj += 2
        notes.append(f"Инсайдеры владеют {ins_pct}%")
    if inst_pct >= 40:
        adj += 1
        notes.append(f"Институционалы {inst_pct}%")
    if adj > 0:
        bias = "bullish"
    if not notes:
        notes.append(f"Инсайдеры {ins_pct}%, институционалы {inst_pct}%")
    return {
        "available": True,
        "kind": "ownership",
        "bias": bias,
        "score_adj": min(adj, 3),
        "label": "Доли держателей",
        "summary": "; ".join(notes),
        "insiders_pct": ins_pct,
        "institutions_pct": inst_pct,
        "window_days": None,
        "recent": [],
    }


def insider_signal(pair: str, market: str | None, region: str | None = None) -> dict:
    """Главная точка: US → SEC Form 4, РФ → доли держателей, иначе N/A."""
    if market != "stock":
        return {"available": False}
    is_ru = (region == "ru") or pair.strip().upper().endswith(".ME")
    try:
        if is_ru:
            from instruments_catalog import resolve_yf_symbol

            return _ru_ownership(resolve_yf_symbol(pair, "stock")) or {"available": False}
        ticker = pair.strip().upper().split(".")[0]
        res = _us_insider(ticker)
        if res:
            return res
        # фолбэк на доли, если CIK не найден
        from instruments_catalog import resolve_yf_symbol

        return _ru_ownership(resolve_yf_symbol(pair, "stock")) or {"available": False}
    except Exception:
        return {"available": False}
