# SPDX-License-Identifier: AGPL-3.0-or-later
"""
insider_backtest.py — генератор HTML-отчёта по insider-сделкам (БЕЗ парсинга).

⚠️ Сетевой парсинг удалён. Скрипт НЕ ходит в SEC/Yahoo и ничего не качает —
   он только читает уже готовый CSV (`insider_trades.csv`), считает винрейт по
   фильтрам (агрегация локальных данных) и собирает самодостаточный HTML-отчёт.
   Зависимостей нет (только стандартная библиотека). Полностью автономен,
   удаляется без последствий для проекта.

ВХОД  : insider_trades.csv  (колонки: txn_date, ticker, action, insider, role,
        shares, price, value, px_entry, ret_21d, win_21d, …)
ВЫХОД : insider_report.html  (тёмная тема, адаптив под телефон) +
        insider_winrate_summary.csv (пересчитанная сводка)

ЗАПУСК
  py insider_backtest.py
  py insider_backtest.py --trades insider_trades.csv --out insider_report.html

ВАЖНО (честно): винрейт — результат правила на исторических данных, не гарантия
будущего. Высокий win% ≠ прибыль (решает матожидание).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows-консоль cp1251 → UTF-8
except (AttributeError, ValueError):
    pass


# ─────────────────────────────── чтение ──────────────────────────────

def read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _f(t: dict, key: str) -> float:
    try:
        return float(t.get(key) or 0)
    except (ValueError, TypeError):
        return 0.0


# ──────────────────────── винрейт по фильтрам ────────────────────────

def _wr(rows: list[dict]) -> dict:
    """Сводка по подмножеству сделок (учитываются только размеченные px_entry>0)."""
    labeled = [t for t in rows if _f(t, "px_entry") > 0]
    n = len(labeled)
    wins = sum(1 for t in labeled if int(_f(t, "win_21d")) == 1)
    avg = sum(_f(t, "ret_21d") for t in labeled) / n if n else 0.0
    return {"trades": n,
            "win_rate_21d": round(wins / n * 100, 1) if n else 0.0,
            "avg_ret_21d_%": round(avg, 2)}


def _cluster_buys(buys: list[dict], window_days: int = 14, min_insiders: int = 2) -> list[dict]:
    """Покупки, где ≥min_insiders разных инсайдера купили один тикер в окне дней."""
    by_tk: dict[str, list[dict]] = defaultdict(list)
    for t in buys:
        if t.get("txn_date"):
            by_tk[t.get("ticker", "")].append(t)
    flagged: list[dict] = []
    for group in by_tk.values():
        group.sort(key=lambda t: t.get("txn_date", ""))
        for t in group:
            try:
                d0 = datetime.strptime(t["txn_date"], "%Y-%m-%d")
            except (ValueError, KeyError):
                continue
            insiders = set()
            for u in group:
                try:
                    du = datetime.strptime(u["txn_date"], "%Y-%m-%d")
                except (ValueError, KeyError):
                    continue
                if 0 <= (du - d0).days <= window_days:
                    insiders.add(u.get("insider"))
            if len(insiders) >= min_insiders:
                flagged.append(t)
    return flagged


def compute_summary(trades: list[dict]) -> list[dict]:
    """Винрейт по срезам-фильтрам — где искать прибыльное правило."""
    buys = [t for t in trades if t.get("action") == "BUY"]
    sells = [t for t in trades if t.get("action") == "SELL"]
    rows: list[dict] = []

    def add(name: str, subset: list[dict]):
        rows.append({"filter": name, **_wr(subset)})

    role = lambda t: (t.get("role") or "").upper()
    add("ВСЕ покупки", buys)
    add("ВСЕ продажи", sells)
    add("Покупки CEO/CFO/President",
        [t for t in buys if any(k in role(t) for k in ("CEO", "CFO", "PRESIDENT", "CHIEF"))])
    add("Покупки директоров", [t for t in buys if "DIRECTOR" in role(t)])
    add("Покупки 10%-держателей", [t for t in buys if "10%OWNER" in role(t)])
    add("Покупки крупные (>$250k)", [t for t in buys if _f(t, "value") > 250_000])
    add("Покупки крупные (>$1M)", [t for t in buys if _f(t, "value") > 1_000_000])
    cluster = _cluster_buys(buys)
    add("Кластерные покупки (≥2 инсайдера/14д)", cluster)
    add("Кластер + крупные (>$250k)", [t for t in cluster if _f(t, "value") > 250_000])
    return rows


# ──────────────────────────── HTML-отчёт (UI) ────────────────────────

def build_html_report(trades: list[dict], summary: list[dict], meta: dict, out: str) -> None:
    """Самодостаточный тёмный HTML-отчёт (без CDN/сети) по insider-данным."""
    # Ограничиваем объём страницы, но НЕ обрезаем покупки: они мельче по $, а
    # именно они — информативный сигнал. Берём ВСЕ покупки + топ продаж по сумме.
    CAP = 1500
    fval = lambda t: _f(t, "value")
    buys = sorted((t for t in trades if t.get("action") == "BUY"), key=fval, reverse=True)
    sells = sorted((t for t in trades if t.get("action") == "SELL"), key=fval, reverse=True)
    picked = (buys + sells[:max(0, CAP - len(buys))])
    picked.sort(key=fval, reverse=True)
    trades_lite = [{
        "d": t.get("txn_date", ""), "tk": t.get("ticker", ""), "a": t.get("action", ""),
        "ins": t.get("insider", ""), "role": t.get("role", ""),
        "sh": _f(t, "shares"), "px": _f(t, "price"),
        "val": fval(t), "r21": _f(t, "ret_21d"),
        "w": int(_f(t, "win_21d")), "pe": _f(t, "px_entry"),
    } for t in picked]

    data_json = json.dumps({"trades": trades_lite, "summary": summary, "meta": meta},
                           ensure_ascii=False)
    _write(out, _HTML_TEMPLATE.replace("/*__DATA__*/", data_json))


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Insider-анализ · TIS research</title>
<style>
:root{--bg:#0b0c12;--card:#14161f;--card2:#1a1d29;--line:rgba(255,255,255,.08);
--txt:#e7e9f0;--mut:#8b90a4;--accent:#6366f1;--accent2:#a855f7;--up:#22c55e;--down:#ef4444;}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 600px at 80% -10%,rgba(168,85,247,.10),transparent),
radial-gradient(1000px 500px at -10% 10%,rgba(99,102,241,.10),transparent),var(--bg);
color:var(--txt);font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;padding:28px;}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:22px;margin:0 0 2px;letter-spacing:.2px}
h1 .g{background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--mut);margin-bottom:18px;font-size:13px}
.warn{background:linear-gradient(90deg,rgba(239,68,68,.10),rgba(168,85,247,.06));border:1px solid rgba(239,68,68,.25);
border-radius:14px;padding:12px 16px;margin:0 0 22px;color:#fca5a5;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:22px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.kpi .v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
.kpi .l{color:var(--mut);font-size:12px;margin-top:2px}
.sec{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin-bottom:22px}
.sec h2{font-size:15px;margin:0 0 14px;font-weight:600}
.bar-row{display:grid;grid-template-columns:280px 1fr 70px 70px;gap:10px;align-items:center;padding:7px 0;border-top:1px solid var(--line)}
.bar-row:first-of-type{border-top:none}
.bar-row .name{color:#cbd0e0;font-size:13px}
.track{height:10px;background:var(--card2);border-radius:6px;overflow:hidden}
.fill{height:100%;border-radius:6px;background:linear-gradient(90deg,var(--accent),var(--accent2))}
.num{text-align:right;font-variant-numeric:tabular-nums;font-size:13px}
.pos{color:var(--up)}.neg{color:var(--down)}.mut{color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-weight:600;cursor:pointer;user-select:none;position:sticky;top:0;background:var(--card)}
th:hover{color:var(--txt)}td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
.tag{padding:1px 8px;border-radius:6px;font-size:11px;font-weight:600}
.buy{background:rgba(34,197,94,.15);color:var(--up)}.sell{background:rgba(239,68,68,.15);color:var(--down)}
.win{color:var(--up)}.loss{color:var(--down)}
.tbl-wrap{max-height:560px;overflow:auto;border-radius:10px}
.ctrls{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap}
select,input{background:var(--card2);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font:inherit}
.foot{color:var(--mut);font-size:12px;margin-top:8px}
/* ───── телефон ───── */
@media(max-width:640px){
  body{padding:14px}
  h1{font-size:19px}.sub{font-size:12px}
  .cards{grid-template-columns:repeat(2,1fr);gap:8px}
  .kpi{padding:11px 12px}.kpi .v{font-size:20px}
  .sec{padding:14px 13px;border-radius:14px}
  /* бары: имя сверху на всю ширину, ниже — шкала и числа */
  .bar-row{grid-template-columns:1fr auto auto;grid-template-rows:auto auto;gap:4px 8px}
  .bar-row .name{grid-column:1/-1}
  .bar-row .track{grid-column:1}
  .bar-row .num:nth-child(3){grid-column:2}
  .bar-row .num:nth-child(4){grid-column:3}
  .ctrls select,.ctrls input{width:100%}
  /* таблица → карточки */
  .tbl-wrap{max-height:none;overflow:visible}
  table,tbody,tr,td{display:block;width:100%}
  thead{display:none}
  tr{border:1px solid var(--line);border-radius:12px;margin-bottom:10px;padding:8px 10px;background:var(--card2)}
  td{border:none;padding:3px 0;display:flex;justify-content:space-between;align-items:center;white-space:normal;gap:12px}
  td::before{content:attr(data-label);color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.3px}
  td.r,td.r{text-align:right}
}
</style></head>
<body><div class="wrap">
<h1>Insider-анализ · <span class="g">умные деньги</span></h1>
<div class="sub" id="sub"></div>
<div class="warn">⚠️ Винрейт — это результат правила на исторических данных, не гарантия будущего.
Высокий win% при бычьем рынке и малой выборке ≠ прибыльная стратегия. Решает матожидание (ср. доходность × частота),
а не сам винрейт. Перед торговлей нужна out-of-sample проверка на падающем рынке и учёт издержек.</div>

<div class="cards" id="kpis"></div>

<div class="sec">
  <h2>Винрейт по фильтрам (исход через 21 торговый день)</h2>
  <div id="bars"></div>
  <div class="foot">Бар = win% (доля сделок, ушедших в нужную сторону). Справа — win% и средняя доходность за 21д.</div>
</div>

<div class="sec">
  <h2>Сделки крупных игроков</h2>
  <div class="ctrls">
    <select id="fAction"><option value="">Все сделки</option><option value="BUY">Покупки</option><option value="SELL">Продажи</option></select>
    <input id="fText" placeholder="поиск: тикер / инсайдер / роль" style="flex:1;min-width:180px">
    <select id="fWin"><option value="">Любой исход</option><option value="1">В плюс (win)</option><option value="0">В минус</option></select>
  </div>
  <div class="tbl-wrap"><table id="tbl"><thead><tr>
    <th data-k="d">Дата</th><th data-k="tk">Тикер</th><th data-k="a">Сделка</th>
    <th data-k="ins">Инсайдер</th><th data-k="role">Роль</th>
    <th class="r" data-k="sh">Акций</th><th class="r" data-k="px">Цена</th>
    <th class="r" data-k="val">Сумма $</th><th class="r" data-k="r21">Δ21д %</th>
  </tr></thead><tbody id="tbody"></tbody></table></div>
  <div class="foot" id="tcount"></div>
</div>
</div>

<script>
const DATA = /*__DATA__*/;
const {trades, summary, meta} = DATA;
const fmt=(n,d=0)=>n.toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});

// подзаголовок
document.getElementById('sub').textContent =
  `Источник: SEC EDGAR Form 4 · период ${meta.period} · компаний: ${meta.companies} · сделок: ${meta.total} · сформировано ${meta.generated}`;

// KPI
// Win% берём из полной сводки (а не из усечённой до 600 таблицы — иначе завышено).
const sumRow=n=>summary.find(s=>s.filter===n)||{};
const buyWr=(sumRow('ВСЕ покупки').win_rate_21d??'—');
const kpis=[
  ['Всего сделок', fmt(meta.total)],
  ['Покупок', fmt(meta.buys)],
  ['Продаж', fmt(meta.sells)],
  ['Win% покупок (21д)', buyWr+'%'],
];
document.getElementById('kpis').innerHTML = kpis.map(k=>
  `<div class="kpi"><div class="v">${k[1]}</div><div class="l">${k[0]}</div></div>`).join('');

// бары винрейта
document.getElementById('bars').innerHTML = summary.map(s=>{
  const wrv=+s.win_rate_21d, av=+s['avg_ret_21d_%'], n=+s.trades;
  const avc = av>0?'pos':(av<0?'neg':'mut');
  return `<div class="bar-row"><div class="name">${s.filter} <span class="mut">(${n})</span></div>
    <div class="track"><div class="fill" style="width:${Math.max(0,Math.min(100,wrv))}%"></div></div>
    <div class="num">${wrv}%</div><div class="num ${avc}">${av>0?'+':''}${av}%</div></div>`;
}).join('');

// таблица
let sortK='val', sortAsc=false;
const tbody=document.getElementById('tbody');
function render(){
  const fa=document.getElementById('fAction').value;
  const fw=document.getElementById('fWin').value;
  const ft=document.getElementById('fText').value.toLowerCase();
  let rows=trades.filter(t=>(!fa||t.a===fa)&&(fw===''||String(t.w)===fw)
    &&(!ft||(t.tk+' '+t.ins+' '+t.role).toLowerCase().includes(ft)));
  rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(typeof x==='string'){return sortAsc?x.localeCompare(y):y.localeCompare(x);}return sortAsc?x-y:y-x;});
  tbody.innerHTML=rows.slice(0,1500).map(t=>{
    const wc=t.pe>0?(t.w?'win':'loss'):'mut';
    return `<tr><td class="mut" data-label="Дата">${t.d}</td><td data-label="Тикер"><b>${t.tk}</b></td>
      <td data-label="Сделка"><span class="tag ${t.a==='BUY'?'buy':'sell'}">${t.a}</span></td>
      <td data-label="Инсайдер">${t.ins}</td><td class="mut" data-label="Роль">${t.role||'—'}</td>
      <td class="r" data-label="Акций">${fmt(t.sh)}</td><td class="r" data-label="Цена">${fmt(t.px,2)}</td>
      <td class="r" data-label="Сумма $">${fmt(t.val)}</td>
      <td class="r ${wc}" data-label="Δ21д %">${t.pe>0?(t.r21>0?'+':'')+fmt(t.r21,2):'—'}</td></tr>`;
  }).join('');
  document.getElementById('tcount').textContent=`показано ${Math.min(rows.length,1500)} из ${rows.length}`;
}
document.querySelectorAll('th').forEach(th=>th.onclick=()=>{
  const k=th.dataset.k;if(k===sortK)sortAsc=!sortAsc;else{sortK=k;sortAsc=false;}render();});
['fAction','fWin','fText'].forEach(id=>document.getElementById(id).oninput=render);
render();
</script></body></html>"""


# ─────────────────────────────── main ────────────────────────────────

def write_csv(path: str, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _meta(trades: list[dict]) -> dict:
    buys = sum(1 for t in trades if t.get("action") == "BUY")
    # Период = окно подачи отчётов (filed_date): отражает реальный диапазон сбора
    # данных, в отличие от txn_date, где у Form 4 бывают старые/битые даты сделок.
    dates = sorted(d for t in trades if (d := t.get("filed_date", "")) and d[:2] == "20")
    period = f"{dates[0]} … {dates[-1]}" if dates else "—"
    return {
        "total": len(trades), "buys": buys, "sells": len(trades) - buys,
        "companies": len({t.get("ticker") for t in trades}),
        "period": period, "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="HTML-отчёт по insider-сделкам из готового CSV (без парсинга).")
    ap.add_argument("--trades", default="insider_trades.csv", help="входной CSV со сделками")
    ap.add_argument("--out", default="insider_report.html", help="выходной HTML-отчёт")
    args = ap.parse_args()

    trades = read_csv(args.trades)
    if not trades:
        print(f"Пусто: в {args.trades} нет сделок.")
        return

    summary = compute_summary(trades)
    write_csv("insider_winrate_summary.csv", summary,
              ["filter", "trades", "win_rate_21d", "avg_ret_21d_%"])
    build_html_report(trades, summary, _meta(trades), args.out)

    print(f"Отчёт собран из {args.trades} ({len(trades)} сделок) → {args.out}")
    print("Сводка → insider_winrate_summary.csv")


if __name__ == "__main__":
    main()
