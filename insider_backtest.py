# SPDX-License-Identifier: AGPL-3.0-or-later
"""
insider_backtest.py — АВТОНОМНЫЙ исследовательский конвейер по сделкам инсайдеров.

⚠️ Файл полностью самостоятельный: НЕ импортирует модули проекта и ничего в нём
   не меняет. Можно удалить в любой момент без последствий.
   Внешние зависимости: только `yfinance` (уже стоит в проекте) + стандартная
   библиотека. SEC EDGAR — без API-ключа.

ЧТО ДЕЛАЕТ
  1. Берёт набор компаний (тикер→CIK из SEC company_tickers.json).
  2. По каждой компании тянет её Form 4 (сделки инсайдеров) за N лет.
  3. Парсит сделки: кто, роль, BUY/SELL, объём, цена, сумма, дата.
  4. РАЗМЕЧАЕТ ИСХОД: форвардная доходность через 5 / 21 / 63 торговых дня
     (дневные цены с Yahoo). Для покупок «win» = цена выросла.
  5. Пишет сырые сделки в CSV и считает ВИНРЕЙТ по срезам-фильтрам
     (роль, размер сделки, кластерные покупки), чтобы увидеть, есть ли в
     данных фильтр с высоким винрейтом.

ВАЖНО (честно): винрейт — это результат ПРАВИЛА на данных, а не свойство самих
данных. Высокий винрейт ≠ прибыль (решает матожидание). Скрипт показывает, что
реально есть в insider-сигналах, без обещаний «70%».

ЗАПУСК
  py insider_backtest.py --years 2 --max-companies 40
  py insider_backtest.py --years 4 --tickers AAPL,NVDA,TSLA,JPM
  py insider_backtest.py --years 4 --max-companies 0      # 0 = все компании (ДОЛГО!)

Результаты: insider_trades.csv (сырьё) + insider_winrate_summary.csv (сводка).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict, fields
from datetime import datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows-консоль cp1251 → UTF-8
except (AttributeError, ValueError):
    pass

# SEC требует осмысленный User-Agent с контактом (иначе 403). Поставьте свой.
USER_AGENT = "TIS-research insider-backtest (contact: research@example.com)"
SEC_THROTTLE = 0.12  # ~8 req/s, ниже лимита SEC (10/s)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"

ACQ_DISP = {"A": "BUY", "D": "SELL"}
HORIZONS = [5, 21, 63]  # торговых дней ≈ неделя / месяц / квартал


# ─────────────────────────────── HTTP ───────────────────────────────

def _get(url: str, retries: int = 3) -> bytes:
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(SEC_THROTTLE)
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"GET fail {url}: {last}")


# ─────────────────────────── Вселенная компаний ──────────────────────

def load_universe(tickers: list[str] | None, max_companies: int) -> list[tuple[str, str]]:
    """Возвращает [(ticker, cik10)]. Если задан список тикеров — только они."""
    raw = json.loads(_get(TICKERS_URL))
    # company_tickers.json: { "0": {cik_str, ticker, title}, ... } по убыванию популярности.
    rows = list(raw.values())
    by_ticker = {r["ticker"].upper(): str(r["cik_str"]).zfill(10) for r in rows}
    if tickers:
        out = [(t, by_ticker[t]) for t in (x.upper() for x in tickers) if t in by_ticker]
        missing = [t for t in (x.upper() for x in tickers) if t not in by_ticker]
        if missing:
            print(f"  ⚠️ не найдены в SEC: {', '.join(missing)}")
        return out
    universe = [(r["ticker"].upper(), str(r["cik_str"]).zfill(10)) for r in rows]
    if max_companies and max_companies > 0:
        universe = universe[:max_companies]
    return universe


# ─────────────────────────── Form 4 за период ────────────────────────

def list_form4(cik10: str, since: datetime) -> list[dict]:
    """Все Form 4 компании с даты `since`: [{accession, doc, filed}]."""
    try:
        data = json.loads(_get(SUBMISSIONS_URL.format(cik10=cik10)))
    except RuntimeError:
        return []
    out: list[dict] = []

    def _harvest(block: dict):
        forms = block.get("form", [])
        accs = block.get("accessionNumber", [])
        docs = block.get("primaryDocument", [])
        dates = block.get("filingDate", [])
        for i, form in enumerate(forms):
            if form != "4":
                continue
            d = dates[i] if i < len(dates) else ""
            if d and d < since.strftime("%Y-%m-%d"):
                continue
            out.append({
                "accession": accs[i] if i < len(accs) else "",
                "doc": docs[i] if i < len(docs) else "",
                "filed": d,
            })

    recent = data.get("filings", {}).get("recent", {})
    _harvest(recent)
    # Старые подачи вынесены в доп.файлы (нужно для охвата 3–4 лет назад).
    for f in data.get("filings", {}).get("files", []):
        name = f.get("name")
        # Тянем доп.файл, только если его диапазон пересекается с нужным периодом.
        if name and (not f.get("filingTo") or f["filingTo"] >= since.strftime("%Y-%m-%d")):
            try:
                extra = json.loads(_get(f"https://data.sec.gov/submissions/{name}"))
                _harvest(extra)
            except RuntimeError:
                continue
    return out


@dataclass
class Trade:
    filed_date: str
    txn_date: str
    insider: str
    role: str
    issuer: str
    ticker: str
    action: str
    security: str
    shares: float
    price: float
    value: float
    shares_after: float
    # размечается позже:
    px_entry: float = 0.0
    ret_5d: float = 0.0
    ret_21d: float = 0.0
    ret_63d: float = 0.0
    win_21d: int = 0       # 1 если форвард-доходность 21д положительна (для BUY)
    accession: str = ""


def _txt(el, path: str, default: str = "") -> str:
    f = el.find(path) if el is not None else None
    return (f.text or default).strip() if f is not None and f.text else default


def _num(el, path: str) -> float:
    try:
        return float(_txt(el, path))
    except (ValueError, TypeError):
        return 0.0


def parse_form4(xml_bytes: bytes, fl: dict, ticker: str) -> list[Trade]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    if "ownershipDocument" not in root.tag:
        return []
    issuer = _txt(root, "issuer/issuerName")
    sym = _txt(root, "issuer/issuerTradingSymbol") or ticker
    owner = root.find("reportingOwner")
    insider = _txt(owner, "reportingOwnerId/rptOwnerName")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    roles = []
    if rel is not None:
        if _txt(rel, "isDirector") in ("1", "true"):
            roles.append("Director")
        if _txt(rel, "isOfficer") in ("1", "true"):
            roles.append(_txt(rel, "officerTitle") or "Officer")
        if _txt(rel, "isTenPercentOwner") in ("1", "true"):
            roles.append("10%Owner")
        if _txt(rel, "isOther") in ("1", "true"):
            roles.append("Other")
    role = ", ".join(roles)

    trades: list[Trade] = []
    for txn in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        amt = txn.find("transactionAmounts")
        code = _txt(txn, "transactionCoding/transactionCode")
        # Берём только реальные рыночные покупки/продажи (code P/S),
        # отсекаем гранты, опционы, дарения и т.п. — они не «сделки трейдера».
        if code not in ("P", "S"):
            continue
        adc = _txt(amt, "transactionAcquiredDisposedCode/value")
        shares = _num(amt, "transactionShares/value")
        price = _num(amt, "transactionPricePerShare/value")
        post = txn.find("postTransactionAmounts")
        trades.append(Trade(
            filed_date=fl["filed"],
            txn_date=_txt(txn, "transactionDate/value"),
            insider=insider,
            role=role,
            issuer=issuer,
            ticker=sym,
            action=ACQ_DISP.get(adc, code),
            security=_txt(txn, "securityTitle/value"),
            shares=shares,
            price=price,
            value=round(shares * price, 2),
            shares_after=_num(post, "sharesOwnedFollowingTransaction/value"),
            accession=fl["accession"],
        ))
    return trades


# ─────────────────────── Разметка исхода (Yahoo) ─────────────────────

def label_outcomes(trades: list[Trade], pad_days: int = 120) -> None:
    """Проставляет форвардную доходность по дневным ценам Yahoo (по тикеру)."""
    import yfinance as yf  # импорт здесь, чтобы файл грузился даже без yfinance

    by_ticker: dict[str, list[Trade]] = {}
    for t in trades:
        by_ticker.setdefault(t.ticker, []).append(t)

    dates = [t.txn_date for t in trades if t.txn_date]
    if not dates:
        return
    start = (datetime.strptime(min(dates), "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    end = (datetime.strptime(max(dates), "%Y-%m-%d") + timedelta(days=pad_days)).strftime("%Y-%m-%d")

    for i, (tk, group) in enumerate(by_ticker.items(), 1):
        try:
            hist = yf.download(tk, start=start, end=end, progress=False, auto_adjust=True)
        except Exception:
            continue
        if hist is None or hist.empty:
            continue
        closes = hist["Close"]
        if hasattr(closes, "columns"):  # MultiIndex при одном тикере
            closes = closes.iloc[:, 0]
        idx = closes.index
        for t in group:
            try:
                d = datetime.strptime(t.txn_date, "%Y-%m-%d")
            except ValueError:
                continue
            pos = idx.searchsorted(d)  # первая торговая дата >= даты сделки
            if pos >= len(idx):
                continue
            entry = float(closes.iloc[pos])
            if entry <= 0:
                continue
            t.px_entry = round(entry, 4)
            for h, attr in zip(HORIZONS, ("ret_5d", "ret_21d", "ret_63d")):
                j = pos + h
                if j < len(closes):
                    setattr(t, attr, round((float(closes.iloc[j]) / entry - 1) * 100, 2))
            # win для покупок: цена через 21д выше; для продаж — ниже (как «шорт-сигнал»).
            if t.action == "BUY":
                t.win_21d = 1 if t.ret_21d > 0 else 0
            elif t.action == "SELL":
                t.win_21d = 1 if t.ret_21d < 0 else 0
        if i % 10 == 0:
            print(f"      размечено тикеров: {i}/{len(by_ticker)}")


# ───────────────────────────── Сводка ────────────────────────────────

def _wr(rows: list[Trade]) -> dict:
    labeled = [t for t in rows if t.px_entry > 0]
    n = len(labeled)
    wins = sum(t.win_21d for t in labeled)
    avg = sum(t.ret_21d for t in labeled) / n if n else 0.0
    return {"trades": n, "win_rate_21d": round(wins / n * 100, 1) if n else 0.0,
            "avg_ret_21d_%": round(avg, 2)}


def build_summary(trades: list[Trade]) -> list[dict]:
    """Винрейт по срезам-фильтрам — где искать прибыльное правило."""
    buys = [t for t in trades if t.action == "BUY"]
    sells = [t for t in trades if t.action == "SELL"]

    rows: list[dict] = []

    def add(name: str, subset: list[Trade]):
        s = _wr(subset)
        rows.append({"filter": name, **s})

    add("ВСЕ покупки", buys)
    add("ВСЕ продажи", sells)
    add("Покупки CEO/CFO/President", [t for t in buys if any(
        k in t.role.upper() for k in ("CEO", "CFO", "PRESIDENT", "CHIEF"))])
    add("Покупки директоров", [t for t in buys if "Director" in t.role])
    add("Покупки 10%-держателей", [t for t in buys if "10%Owner" in t.role])
    add("Покупки крупные (>$250k)", [t for t in buys if t.value > 250_000])
    add("Покупки крупные (>$1M)", [t for t in buys if t.value > 1_000_000])

    # Кластерные покупки: ≥2 разных инсайдера купили один тикер в окне 14 дней.
    cluster = _cluster_buys(buys, window_days=14, min_insiders=2)
    add("Кластерные покупки (≥2 инсайдера/14д)", cluster)
    add("Кластер + крупные (>$250k)", [t for t in cluster if t.value > 250_000])

    return rows


def _cluster_buys(buys: list[Trade], window_days: int, min_insiders: int) -> list[Trade]:
    from collections import defaultdict
    by_tk: dict[str, list[Trade]] = defaultdict(list)
    for t in buys:
        if t.txn_date:
            by_tk[t.ticker].append(t)
    flagged: list[Trade] = []
    for group in by_tk.values():
        group.sort(key=lambda t: t.txn_date)
        for i, t in enumerate(group):
            try:
                d0 = datetime.strptime(t.txn_date, "%Y-%m-%d")
            except ValueError:
                continue
            insiders = set()
            for u in group:
                try:
                    du = datetime.strptime(u.txn_date, "%Y-%m-%d")
                except ValueError:
                    continue
                if 0 <= (du - d0).days <= window_days:
                    insiders.add(u.insider)
            if len(insiders) >= min_insiders:
                flagged.append(t)
    return flagged


# ─────────────────────────────── main ────────────────────────────────

def write_csv(path: str, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Парсер insider-сделок + разметка исхода + винрейт.")
    ap.add_argument("--years", type=float, default=2, help="глубина истории в годах (по умолч. 2)")
    ap.add_argument("--max-companies", type=int, default=40,
                    help="сколько компаний из топа SEC (0 = все, ДОЛГО). По умолч. 40")
    ap.add_argument("--tickers", type=str, default="",
                    help="свой список тикеров через запятую (переопределяет --max-companies)")
    ap.add_argument("--out", type=str, default="insider_trades.csv")
    args = ap.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=int(args.years * 365))
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] or None

    print(f"[1/4] Вселенная компаний (с {since.date()})…")
    universe = load_universe(tickers, args.max_companies)
    print(f"      компаний к обходу: {len(universe)}")

    print("[2/4] Тяну и парсю Form 4 по компаниям…")
    all_trades: list[Trade] = []
    for i, (tk, cik10) in enumerate(universe, 1):
        cik = str(int(cik10))  # без ведущих нулей для пути архива
        for fl in list_form4(cik10, since):
            # primaryDocument часто указывает на HTML-рендер вида "xslF345X06/form4.xml".
            # Сырой XML лежит по базовому имени в корне папки подачи — берём basename.
            doc = fl["doc"].split("/")[-1]
            if not doc.lower().endswith(".xml"):
                continue
            url = ARCHIVE.format(cik=cik, acc_nodash=fl["accession"].replace("-", ""), doc=doc)
            try:
                xml = _get(url)
            except RuntimeError:
                continue
            all_trades.extend(parse_form4(xml, fl, tk))
        if i % 5 == 0 or i == len(universe):
            print(f"      {i}/{len(universe)} компаний, P/S-сделок: {len(all_trades)}")

    if not all_trades:
        print("Сделок не найдено (за период не было рыночных покупок/продаж P/S).")
        return

    print(f"[3/4] Размечаю исход по ценам Yahoo ({len(all_trades)} сделок)…")
    label_outcomes(all_trades)

    all_trades.sort(key=lambda t: t.value, reverse=True)
    write_csv(args.out, [asdict(t) for t in all_trades], [f.name for f in fields(Trade)])

    print("[4/4] Считаю винрейт по фильтрам…")
    summary = build_summary(all_trades)
    write_csv("insider_winrate_summary.csv", summary, ["filter", "trades", "win_rate_21d", "avg_ret_21d_%"])

    print(f"\nСырьё → {args.out}  ({len(all_trades)} сделок)")
    print("Сводка → insider_winrate_summary.csv\n")
    print(f"{'ФИЛЬТР':<42}{'СДЕЛОК':>8}{'WIN%(21д)':>12}{'СР.ДОХ%':>10}")
    for r in summary:
        print(f"{r['filter']:<42}{r['trades']:>8}{r['win_rate_21d']:>12}{r['avg_ret_21d_%']:>10}")
    print("\n⚠️ Винрейт — результат правила на истории, не гарантия будущего. "
          "Высокий win% без хорошего ср.дохода ≠ прибыль (смотрите матожидание).")


if __name__ == "__main__":
    main()
