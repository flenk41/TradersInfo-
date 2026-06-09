# SPDX-License-Identifier: AGPL-3.0-or-later
"""
signal_scan.py — массовое наполнение журнала сигналов по каталогу (long/short).

Гоняет РЕАЛЬНЫЙ движок (engine.analyze_pair) по инструментам каталога, берёт
рекомендацию (accuracy.recommended_side), ОТБРАСЫВАЕТ «wait» и собирает записи
журнала ТОЙ ЖЕ логикой, что и форма в приложении (calculate_position /
zone_stop_take) — entry = текущая цена, стоп/тейк/R:R от неё.

Результат:
  research/signals_journal.json — массив записей, готовый к импорту в журнал
      (localStorage ключ `signal_journal`);
  research/signals_scan.csv     — то же в читаемом виде.

⚠️ Зависит от пакета tis (использует движок), но НИЧЕГО в приложении не меняет и
   ничем не импортируется — удаляется без последствий.
⚠️ Полная вселенная (тысячи тикеров) непрактична: часы счёта + в РФ Binance
   заблокирован + журнал-localStorage не тянет тысячи записей. По умолчанию —
   каталог приложения (крипта + акции США/РФ ≈ 156), это и есть «все акции и крипта».

Запуск:
  py research/signal_scan.py                     # весь каталог
  py research/signal_scan.py --markets crypto    # только крипта
  py research/signal_scan.py --max 40 --workers 6
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from tis.engine import analyze_pair
from tis.analysis.position_calculator import PositionInput, calculate_position
from tis.features.signal_journal import build_record
from tis.data.instruments_catalog import CRYPTO_LIST, STOCKS_US, STOCKS_RU


def _universe(markets: list[str]):
    out = []
    if "crypto" in markets:
        out += CRYPTO_LIST
    if "us" in markets:
        out += STOCKS_US
    if "ru" in markets:
        out += STOCKS_RU
    return out


def _scan_one(inst) -> dict | None:
    """Анализ одного инструмента → запись журнала, либо None (wait/ошибка)."""
    try:
        a = analyze_pair(inst.id, market=inst.market)
    except Exception:
        return {"_error": inst.id}
    side = getattr(getattr(a, "accuracy", None), "recommended_side", "wait")
    if side not in ("long", "short"):
        return None  # «wait» — пропускаем по условию задачи
    try:
        pos = calculate_position(a, PositionInput(a.price, 100, 10, side))
        rec = build_record({
            "pair": inst.id,
            "market": inst.market,
            # Показываем И название, И тикер — иначе крипта (по имени «Avalanche»)
            # неотличима от акций в журнале (не виден /USDT).
            "display": f"{getattr(inst, 'name', inst.id)} ({inst.id})",
            "side": side,
            "entry": a.price,
            "stop": pos.stop_loss,
            "take_profit": pos.take_profit,
            "take_profit_2": pos.take_profit_2,
            "accuracy_pct": round(float(a.accuracy.overall_pct), 1),
        })
        return rec
    except Exception:
        return {"_error": inst.id}


def main() -> None:
    ap = argparse.ArgumentParser(description="Массовое наполнение журнала сигналов (long/short, без wait).")
    ap.add_argument("--markets", default="crypto,us,ru", help="через запятую: crypto,us,ru (по умолч. все)")
    ap.add_argument("--max", type=int, default=0, help="ограничить число инструментов (0 = все)")
    ap.add_argument("--workers", type=int, default=6, help="параллельных анализов (по умолч. 6)")
    ap.add_argument("--out-json", default="signals_journal.json")
    ap.add_argument("--out-csv", default="signals_scan.csv")
    args = ap.parse_args()

    markets = [m.strip() for m in args.markets.split(",") if m.strip()]
    universe = _universe(markets)
    if args.max > 0:
        universe = universe[: args.max]

    print(f"[1/2] Анализ {len(universe)} инструментов ({', '.join(markets)}), движок analyze_pair…")
    print("      Берём только long/short (wait отбрасываем). Это займёт несколько минут.")

    records: list[dict] = []
    errors = 0
    waits = 0
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_scan_one, inst): inst for inst in universe}
        for fut in as_completed(futures):
            done += 1
            r = fut.result()
            if r is None:
                waits += 1
            elif "_error" in r:
                errors += 1
            else:
                records.append(r)
            if done % 10 == 0 or done == len(universe):
                el = time.time() - t0
                print(f"      {done}/{len(universe)} | сигналов: {len(records)} | wait: {waits} | ошибок: {errors} | {el:.0f}с")

    # Сортируем по баллу (сильные сигналы сверху).
    records.sort(key=lambda r: r.get("accuracy_pct") or 0, reverse=True)

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    longs = sum(1 for r in records if r["side"] == "long")
    shorts = len(records) - longs
    cols = ["display", "pair", "market", "side", "entry", "stop", "take_profit", "rr", "accuracy_pct"]
    with open(args.out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)

    print(f"\n[2/2] Готово за {time.time()-t0:.0f}с")
    print(f"  Сигналов: {len(records)}  (бычьих/long: {longs}, медвежьих/short: {shorts})")
    print(f"  Пропущено wait: {waits} | ошибок анализа: {errors}")
    print(f"  → {args.out_json}  (импорт в журнал: localStorage 'signal_journal')")
    print(f"  → {args.out_csv}")
    print("\nТОП-8 по баллу:")
    for r in records[:8]:
        print(f"  {r['side']:5} {r['display'][:24]:24} вход {r['entry']:<12} стоп {r['stop']:<12} тейк {r['take_profit']:<12} R:R 1:{r['rr']} балл {r['accuracy_pct']}")


if __name__ == "__main__":
    main()
