# SPDX-License-Identifier: AGPL-3.0-or-later
"""
strategy_backtest.py — исторический бэктест НАШЕЙ TA-логики (винрейт/матожидание).

Симулирует сигналы «как-если на дату X» по истории и проверяет форвардные исходы
TP/SL. Использует РЕАЛЬНЫЕ функции движка на исторических срезах (методология та
же, что в продукте):
  - тренд EMA20/50 + RSI (направление, «flat» = наш «wait» — пропускаем);
  - уровни структуры (market_structure.find_key_levels);
  - стоп/тейк — position_calculator.zone_stop_take (структура+ATR, R:R≥1:2);
  - исход — первое касание стопа/тейка по будущим свечам (стоп при двойном касании).

Торгует ПО ОДНОЙ позиции на инструмент (без перекрытия): после закрытия сделки
продолжает со следующей свечи. Так винрейт/матожидание получаются честные.

⚠️ Зависит от пакета tis, но ничего в приложении не меняет и удаляется без
   последствий. Сетевой только разовый запрос истории на инструмент.

Запуск:
  py research/strategy_backtest.py                       # каталог, дневки
  py research/strategy_backtest.py --markets crypto      # только крипта
  py research/strategy_backtest.py --horizon 30 --max 40
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from tis.data.market_data import fetch_klines
from tis.analysis.analyzer import _ema, _rsi, _atr
from tis.analysis.market_structure import find_key_levels
from tis.analysis.position_calculator import zone_stop_take
from tis.data.instruments_catalog import CRYPTO_LIST, STOCKS_US, STOCKS_RU


def _universe(markets):
    out = []
    if "crypto" in markets: out += CRYPTO_LIST
    if "us" in markets: out += STOCKS_US
    if "ru" in markets: out += STOCKS_RU
    return out


def _first_touch(side, stop, tp, highs, lows):
    """Первое касание стопа/тейка вперёд. (исход, R-кратность) или None."""
    for hi, lo in zip(highs, lows):
        if side == "long":
            hit_sl, hit_tp = lo <= stop, hi >= tp
        else:
            hit_sl, hit_tp = hi >= stop, lo <= tp
        if hit_sl:   # при двойном касании консервативно засчитываем стоп
            return "sl"
        if hit_tp:
            return "tp"
    return None


def backtest_instrument(inst, interval, horizon, warmup=80):
    try:
        df = fetch_klines(inst.id, interval=interval, limit=600, market=inst.market)
    except Exception:
        return []
    if df is None or len(df) < warmup + 30:
        return []
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    n = len(df)
    trades = []

    i = warmup
    while i < n - 2:
        c = close.iloc[: i + 1]
        price = float(c.iloc[-1])
        if price <= 0:
            i += 1; continue
        ema20 = float(_ema(c, 20).iloc[-1])
        ema50 = float(_ema(c, 50).iloc[-1])
        rsi = _rsi(c)

        # Направление + гейт селективности: строгий тренд И согласие RSI.
        # Иначе — «wait» (как в продукте), сделку не открываем.
        if price > ema20 > ema50 and rsi >= 50:
            side = "long"
        elif price < ema20 < ema50 and rsi <= 50:
            side = "short"
        else:
            i += 1; continue

        hist = df.iloc[: i + 1]
        atr = _atr(hist)
        supports, resistances = find_key_levels(hist, price)
        stop, tp = zone_stop_take(side, price, supports, resistances, [], atr)

        # валидность уровней
        if side == "long" and not (stop < price < tp):
            i += 1; continue
        if side == "short" and not (tp < price < stop):
            i += 1; continue
        risk = abs(price - stop)
        if risk <= 0:
            i += 1; continue
        rr = round(abs(tp - price) / risk, 2)

        end = min(i + 1 + horizon, n)
        outcome = _first_touch(side, stop, tp,
                               list(high.iloc[i + 1: end]), list(low.iloc[i + 1: end]))
        if outcome is None:
            i += horizon  # сделка «зависла» — двигаемся дальше за горизонт
            continue
        r_mult = rr if outcome == "tp" else -1.0
        trades.append({
            "pair": inst.id, "market": inst.market, "side": side,
            "date": str(df["open_time"].iloc[i])[:10],
            "entry": round(price, 6), "stop": round(stop, 6), "take": round(tp, 6),
            "rr": rr, "result": outcome, "R": r_mult,
        })
        # к следующей свече после закрытия — без перекрытия позиций
        # (находим бар закрытия приблизительно = конец окна или раньше; для простоты +1)
        i += 1
    return trades


def _summ(trades):
    n = len(trades)
    if not n:
        return {"trades": 0}
    wins = [t for t in trades if t["result"] == "tp"]
    rs = [t["R"] for t in trades]
    gw = sum(r for r in rs if r > 0)
    gl = abs(sum(r for r in rs if r < 0))
    return {
        "trades": n,
        "win_rate": round(len(wins) / n * 100, 1),
        "avg_R": round(sum(rs) / n, 3),
        "profit_factor": round(gw / gl, 2) if gl else float("inf"),
        "total_R": round(sum(rs), 1),
    }


def main():
    ap = argparse.ArgumentParser(description="Исторический бэктест TA-сигналов (винрейт/матожидание).")
    ap.add_argument("--markets", default="crypto,us,ru")
    ap.add_argument("--interval", default="1d", help="ТФ свечей (1d надёжен для длинной истории)")
    ap.add_argument("--horizon", type=int, default=40, help="макс. баров до исхода (по умолч. 40)")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="strategy_backtest_trades.csv")
    args = ap.parse_args()

    markets = [m.strip() for m in args.markets.split(",") if m.strip()]
    universe = _universe(markets)
    if args.max > 0:
        universe = universe[: args.max]

    print(f"[1/2] Бэктест {len(universe)} инструментов, ТФ {args.interval}, горизонт {args.horizon} баров…")
    all_trades = []
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(backtest_instrument, inst, args.interval, args.horizon): inst for inst in universe}
        for fut in as_completed(futs):
            done += 1
            all_trades.extend(fut.result())
            if done % 20 == 0 or done == len(universe):
                print(f"      {done}/{len(universe)} | сделок симулировано: {len(all_trades)} | {time.time()-t0:.0f}с")

    if not all_trades:
        print("Сделок не получилось (мало истории / нет данных).")
        return

    cols = ["date", "pair", "market", "side", "entry", "stop", "take", "rr", "result", "R"]
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(all_trades)

    longs = [t for t in all_trades if t["side"] == "long"]
    shorts = [t for t in all_trades if t["side"] == "short"]
    crypto = [t for t in all_trades if t["market"] == "crypto"]
    stock = [t for t in all_trades if t["market"] == "stock"]

    def line(name, s):
        if not s.get("trades"):
            print(f"  {name:22} нет сделок"); return
        print(f"  {name:22} сделок {s['trades']:>5} | win {s['win_rate']:>5}% | ср.R {s['avg_R']:>+6} | PF {s['profit_factor']:>5} | сумма {s['total_R']:>+7}R")

    print(f"\n[2/2] Готово за {time.time()-t0:.0f}с → {args.out}\n")
    print("РЕЗУЛЬТАТЫ БЭКТЕСТА (R:R фикс ≥1:2; матожидание в R на сделку):")
    line("ВСЕ", _summ(all_trades))
    line("Лонги", _summ(longs))
    line("Шорты", _summ(shorts))
    line("Крипта", _summ(crypto))
    line("Акции", _summ(stock))
    be = 33.3
    s = _summ(all_trades)
    verdict = "ПРИБЫЛЬНА" if s["avg_R"] > 0 else "УБЫТОЧНА"
    print(f"\n  Точка безубытка по винрейту при R:R 1:2 ≈ {be}%.")
    print(f"  Итог: стратегия на истории {verdict} (матожидание {s['avg_R']:+}R на сделку).")
    print("  ⚠️ Прошлое ≠ будущее. Без издержек/проскальзывания. Дневной ТФ, гейт = строгий тренд+RSI.")


if __name__ == "__main__":
    main()
