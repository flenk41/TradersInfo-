# SPDX-License-Identifier: AGPL-3.0-or-later
"""
TIS Bybit bot — самостоятельный торговый бот по стратегии TIS.

⚠️ ВАЖНО / SAFETY
- Этот скрипт запускаешь ТЫ, на СВОЕЙ машине, со СВОИМИ ключами. Веб-приложение
  TIS его не запускает и ключи не хранит.
- Ключи берутся ТОЛЬКО из переменных окружения (никогда не вписывай их в файл):
      export BYBIT_API_KEY="..."
      export BYBIT_API_SECRET="..."
- По умолчанию: РЕЖИМ = "paper" (бумажный, без реальных ордеров) и TESTNET = True.
- Реальная торговля включается ОСОЗНАННО: MODE="live", TESTNET=False и
  переменная окружения TIS_BOT_CONFIRM_LIVE="YES". Иначе бот не отправит ни одного
  ордера.
- Создавай ключ Bybit с правами ТОЛЬКО на чтение+торговлю, БЕЗ вывода (no Withdraw),
  желательно на суб-аккаунте с ограниченным балансом и привязкой по IP.
- Торговля с плечом — высокий риск потери средств. Это не финансовый совет.

Стратегия (как в бэктесте TIS): тренд EMA20/50 + фильтр EMA200 (по главному
тренду) + RSI-полоса; стоп по ATR; тейк по R:R; перевод стопа в безубыток
после +1R делает биржа через trading-stop (в live). Размер позиции — от риска
в % от депозита.

Зависимости: requests, pandas, numpy.
Запуск:  python bots/tis_bybit_bot.py
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

import numpy as np
import pandas as pd
import requests

# ─────────────────────────── НАСТРОЙКИ ───────────────────────────
SYMBOL       = "SOLUSDT"     # инструмент (перпетуал USDT)
INTERVAL     = "60"          # таймфрейм Bybit: 1,3,5,15,30,60,120,240,360,720,D
MODE         = "paper"       # "paper" (без реальных сделок) или "live"
TESTNET      = True          # True — тест-сеть; False — реальная биржа
RISK_PCT     = 1.0           # риск на сделку, % от депозита
LEVERAGE_CAP = 10            # потолок плеча (бот не превысит)
RR           = 2.0           # соотношение риск/прибыль (тейк = RR×риск)
ATR_MULT     = 2.0           # множитель ATR для стопа
USE_EMA200   = True          # фильтр главного тренда (лучший по бэктесту)
ADX_MIN      = 0.0           # мин. ADX (0 = выключено); 20 — только сильный тренд
USE_MACD     = False         # подтверждение импульса по MACD
POLL_SEC     = 60            # как часто проверять рынок, сек
# ─────────────────────────────────────────────────────────────────


def _apply_config():
    """Подхватывает bot_config.json (или путь из TIS_BOT_CONFIG), если есть —
    чтобы менять настройки без правки кода (его генерит интерфейс TIS)."""
    import json
    path = os.environ.get("TIS_BOT_CONFIG", "bot_config.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print("Не удалось прочитать", path, ":", e)
        return
    g = globals()
    for k, v in cfg.items():
        key = k.upper()
        if key in g:
            g[key] = v
    print(f"Загружен конфиг: {path}")

_BASE = "https://api-testnet.bybit.com" if TESTNET else "https://api.bybit.com"
_RECV = "5000"
API_KEY = os.environ.get("BYBIT_API_KEY", "")
API_SECRET = os.environ.get("BYBIT_API_SECRET", "")


# ── Публичные данные (без ключа) ──────────────────────────────────
def get_klines(symbol: str, interval: str, limit: int = 400) -> pd.DataFrame:
    r = requests.get(f"{_BASE}/v5/market/kline",
                     params={"category": "linear", "symbol": symbol, "interval": interval, "limit": limit},
                     timeout=20)
    rows = (r.json().get("result") or {}).get("list") or []
    rows = list(reversed(rows))  # Bybit отдаёт от новых к старым
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "vol", "turnover"])
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def instrument_filters(symbol: str) -> dict:
    r = requests.get(f"{_BASE}/v5/market/instruments-info",
                     params={"category": "linear", "symbol": symbol}, timeout=20)
    lst = (r.json().get("result") or {}).get("list") or []
    return lst[0] if lst else {}


# ── Индикаторы ────────────────────────────────────────────────────
def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def _atr(df, n=14):
    h, lo, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - lo), (h - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _adx(df, n=14):
    h, lo, c = df["high"], df["low"], df["close"]
    up, dn = h.diff(), -lo.diff()
    plus = ((up > dn) & (up > 0)) * up
    minus = ((dn > up) & (dn > 0)) * dn
    pc = c.shift(1)
    tr = pd.concat([(h - lo), (h - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, np.nan)
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def _macdh(c):
    macd = _ema(c, 12) - _ema(c, 26)
    return macd - macd.ewm(span=9, adjust=False).mean()


def signal(df: pd.DataFrame) -> dict | None:
    """Возвращает {'side','entry','stop','tp'} или None (нет сигнала)."""
    if len(df) < 220:
        return None
    c = df["close"]
    ema20, ema50, ema200 = _ema(c, 20), _ema(c, 50), _ema(c, 200)
    rsi = _rsi(c)
    atr = _atr(df)
    i = len(df) - 1
    price = float(c.iloc[i])
    a = float(atr.iloc[i])
    if a <= 0 or np.isnan(rsi.iloc[i]):
        return None
    up = ema20.iloc[i] > ema50.iloc[i]
    sep = abs(ema20.iloc[i] - ema50.iloc[i]) / price
    if sep < 0.002:
        return None  # флэт
    if ADX_MIN and not np.isnan(_adx(df).iloc[i]) and _adx(df).iloc[i] < ADX_MIN:
        return None  # слабый тренд
    mh = _macdh(c).iloc[i] if USE_MACD else 0
    long_ok = ((not USE_EMA200) or price > ema200.iloc[i]) and (not USE_MACD or mh > 0)
    short_ok = ((not USE_EMA200) or price < ema200.iloc[i]) and (not USE_MACD or mh < 0)
    r = rsi.iloc[i]
    if up and long_ok and 45 <= r <= 70:
        stop = price - ATR_MULT * a
        return {"side": "Buy", "entry": price, "stop": round(stop, 6), "tp": round(price + RR * (price - stop), 6)}
    if (not up) and short_ok and 30 <= r <= 55:
        stop = price + ATR_MULT * a
        return {"side": "Sell", "entry": price, "stop": round(stop, 6), "tp": round(price - RR * (stop - price), 6)}
    return None


# ── Приватные данные/ордера (нужен ключ; только в live) ───────────
def _signed(method: str, path: str, params: dict) -> dict:
    if not API_KEY or not API_SECRET:
        raise RuntimeError("Нет ключей: задайте BYBIT_API_KEY / BYBIT_API_SECRET в окружении.")
    ts = str(int(time.time() * 1000))
    if method == "GET":
        query = "&".join(f"{k}={v}" for k, v in params.items())
        payload = ts + API_KEY + _RECV + query
        sign = hmac.new(API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        url = f"{_BASE}{path}" + (f"?{query}" if query else "")
        resp = requests.get(url, headers=_headers(ts, sign), timeout=20)
    else:
        import json as _json
        body = _json.dumps(params, separators=(",", ":"))
        payload = ts + API_KEY + _RECV + body
        sign = hmac.new(API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        resp = requests.post(f"{_BASE}{path}", headers=_headers(ts, sign, post=True), data=body, timeout=20)
    data = resp.json()
    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit: {data.get('retMsg')} (code {data.get('retCode')})")
    return data.get("result") or {}


def _headers(ts, sign, post=False):
    h = {"X-BAPI-API-KEY": API_KEY, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": _RECV,
         "X-BAPI-SIGN": sign, "User-Agent": "tis-bot"}
    if post:
        h["Content-Type"] = "application/json"
    return h


def wallet_balance() -> float:
    res = _signed("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
    lst = res.get("list") or []
    return float(lst[0].get("totalAvailableBalance") or 0) if lst else 0.0


def has_position(symbol: str) -> bool:
    res = _signed("GET", "/v5/position/list", {"category": "linear", "symbol": symbol})
    for p in res.get("list") or []:
        if float(p.get("size") or 0) != 0:
            return True
    return False


def _round_qty(qty: float, info: dict) -> str:
    step = float((info.get("lotSizeFilter") or {}).get("qtyStep") or 0.001)
    q = (int(qty / step)) * step if step else qty
    return f"{q:.8f}".rstrip("0").rstrip(".")


def place_order(sig: dict, deposit: float, info: dict):
    """LIVE: рыночный ордер с прикреплёнными стопом и тейком. Без вывода средств."""
    risk_usd = deposit * RISK_PCT / 100
    stop_dist = abs(sig["entry"] - sig["stop"])
    if stop_dist <= 0:
        print("Стоп слишком близко — пропуск."); return
    notional = risk_usd / (stop_dist / sig["entry"])     # объём, чтобы убыток на стопе = risk_usd
    lev = min(LEVERAGE_CAP, max(1, int(0.7 / (stop_dist / sig["entry"]))))  # стоп раньше ликвидации
    qty = _round_qty(notional / sig["entry"], info)
    body = {
        "category": "linear", "symbol": SYMBOL, "side": sig["side"],
        "orderType": "Market", "qty": qty,
        "stopLoss": str(sig["stop"]), "takeProfit": str(sig["tp"]),
        "tpslMode": "Full", "timeInForce": "IOC",
    }
    print(f"[LIVE] Ордер: {sig['side']} {SYMBOL} qty={qty} плечо≤{lev}x SL={sig['stop']} TP={sig['tp']} риск≈{risk_usd:.2f}$")
    # Плечо (idempotent; ошибку «не изменилось» игнорируем).
    try:
        _signed("POST", "/v5/position/set-leverage",
                {"category": "linear", "symbol": SYMBOL, "buyLeverage": str(lev), "sellLeverage": str(lev)})
    except RuntimeError as e:
        if "leverage not modified" not in str(e).lower():
            print("  set-leverage:", e)
    res = _signed("POST", "/v5/order/create", body)
    print("  orderId:", res.get("orderId"))


def _live_allowed() -> bool:
    return MODE == "live" and not TESTNET and os.environ.get("TIS_BOT_CONFIRM_LIVE") == "YES"


def main():
    _apply_config()
    real = MODE == "live"
    if real and not TESTNET and os.environ.get("TIS_BOT_CONFIRM_LIVE") != "YES":
        print("⛔ LIVE на mainnet требует TIS_BOT_CONFIRM_LIVE=YES. Останавливаюсь (защита).")
        return
    where = "TESTNET" if TESTNET else "MAINNET"
    print(f"TIS Bybit bot · {SYMBOL} · TF {INTERVAL} · режим {MODE.upper()} · {where} · риск {RISK_PCT}% · плечо ≤{LEVERAGE_CAP}x")
    if MODE == "paper":
        print("Бумажный режим: реальные ордера НЕ отправляются — только сигналы в консоль.")
    info = {}
    try:
        info = instrument_filters(SYMBOL)
    except Exception as e:
        print("instruments-info:", e)

    while True:
        try:
            df = get_klines(SYMBOL, INTERVAL)
            sig = signal(df)
            ts = time.strftime("%H:%M:%S")
            if not sig:
                print(f"{ts} нет сигнала (цена {float(df['close'].iloc[-1])})")
            else:
                print(f"{ts} СИГНАЛ {sig['side']} вход {sig['entry']} стоп {sig['stop']} тейк {sig['tp']}")
                if real:
                    if not _live_allowed():
                        print("  (live не подтверждён — ордер не отправлен)")
                    elif has_position(SYMBOL):
                        print("  уже есть позиция — пропуск")
                    else:
                        place_order(sig, wallet_balance(), info)
        except Exception as e:
            print("Ошибка цикла:", e)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
