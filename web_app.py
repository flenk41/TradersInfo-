# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 flenk41 (Trading Info Stats). Dual-licensed: AGPL-3.0 or a
# commercial license (see COMMERCIAL.md).
"""Веб-интерфейс с кнопками для торгового помощника."""

from __future__ import annotations

import json
import os
import time
import webbrowser
from collections import defaultdict, deque
from functools import wraps
from threading import Lock, Timer

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from flask import Flask, jsonify, render_template, request

from tis.data.instruments_catalog import catalog_for_frontend, list_instruments
from tis.core.data_cache import get_cached, invalidate
from tis.engine import analyze_pair
from tis.core.formatter import format_analysis, format_position
from tis.data.market_data import fetch_funding_history, fetch_klines, fetch_ticker_24h
from tis.core.markets import MarketDataError, detect_market, normalize_pair, to_tradingview_symbol
from tis.analysis.position_calculator import PositionInput, calculate_position
from tis.core.serialization import analysis_to_dict, position_to_dict

app = Flask(__name__, template_folder="templates", static_folder="static")

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# --- Заголовки безопасности ------------------------------------------------
# CSP подобран под реальные ресурсы фронта: lightweight-charts (unpkg),
# Google Fonts, TradingView (script + iframe). 'unsafe-inline' оставлен, т.к.
# в index.html есть инлайн-скрипты/стили (сборщика нет — vanilla). connect-src
# разрешает 'self' (AI-ключи BYOK шлются на наш сервер, он сам ходит к провайдерам).
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com https://s.tradingview.com https://www.tradingview.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-src https://www.tradingview.com https://s.tradingview.com; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
)


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    # HSTS включаем только под HTTPS (за reverse-proxy), иначе ломает локальный http.
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp

# --- Простой in-memory rate-limit на IP+эндпоинт ---------------------------
# Защищает апстрим-источники (Binance/Yahoo/MOEX/Google) и платный OpenAI от
# случайного флуда. Это локальный/одно-процессный лимитер; для многопроцессного
# прод-развёртывания нужен общий бэкенд (Redis) — здесь достаточно для инструмента.
# Отключается переменной окружения RATE_LIMIT_OFF=1.
_RL_OFF = os.environ.get("RATE_LIMIT_OFF") == "1"
_rl_lock = Lock()
_rl_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(max_calls: int, window_sec: int = 60):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if _RL_OFF:
                return fn(*args, **kwargs)
            ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "?")
                  .split(",")[0].strip())
            key = f"{ip}:{request.endpoint}"
            now = time.time()
            with _rl_lock:
                hits = _rl_hits[key]
                while hits and now - hits[0] > window_sec:
                    hits.popleft()
                if len(hits) >= max_calls:
                    retry = int(window_sec - (now - hits[0])) + 1
                    resp = jsonify({
                        "ok": False,
                        "error": f"Слишком много запросов. Повторите через ~{retry} с.",
                    })
                    resp.headers["Retry-After"] = str(retry)
                    return resp, 429
                hits.append(now)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def _asset_version() -> str:
    """Версия статики по времени изменения файлов — для сброса кэша браузера."""
    try:
        names = ("app.js", "chart.js", "i18n.js", "style.css", "terminal.css", "tradingview.js")
        latest = max(
            os.path.getmtime(os.path.join(_STATIC_DIR, n))
            for n in names
            if os.path.exists(os.path.join(_STATIC_DIR, n))
        )
        return str(int(latest))
    except Exception:
        return "1"


@app.route("/")
def index():
    return render_template(
        "index.html",
        instrument_catalog=json.dumps(catalog_for_frontend(), ensure_ascii=False),
        asset_version=_asset_version(),
    )


@app.route("/api/instruments")
def api_instruments():
    market = request.args.get("market", "crypto").strip().lower()
    region = request.args.get("region", "all").strip().lower()
    if market not in ("crypto", "stock", "forex"):
        return jsonify({"ok": False, "error": "Неверный рынок"}), 400
    return jsonify({"ok": True, "items": list_instruments(market, region)})


@app.route("/api/instruments/search")
@rate_limit(60, 60)
def api_instruments_search():
    market = _market_param() or "crypto"
    region = request.args.get("region", "all").strip().lower()
    if region not in ("ru", "us", "all"):
        region = "all"
    q = request.args.get("q", "").strip()
    try:
        from tis.data.universe import search_universe

        items = search_universe(market, region, q)
        return jsonify({"ok": True, "items": items, "count": len(items)})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Поиск недоступен: {e}"}), 500


def _market_param() -> str | None:
    m = request.args.get("market", "").strip().lower()
    return m if m in ("crypto", "stock", "forex") else None


def _lang_param() -> str:
    return "en" if request.args.get("lang", "ru").strip().lower() == "en" else "ru"


def _bt_filters() -> dict:
    """Фильтры бэктеста из query (ema200/adx/macd). По умолчанию — только EMA200."""
    def _b(name, default):
        v = request.args.get(name)
        if v is None:
            return default
        return v.strip().lower() in ("1", "true", "on", "yes")
    return {
        "use_ema200": _b("ema200", True),
        "adx_min": 20.0 if _b("adx", False) else 0.0,
        "use_macd": _b("macd", False),
    }


@app.route("/api/analyze")
@rate_limit(30, 60)
def api_analyze():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    # Источник крипто-данных: bybit → публичный Bybit V5, иначе авто (Binance→Yahoo).
    source = request.args.get("source", "").strip().lower()
    if source != "bybit":
        source = None
    if not pair:
        return jsonify({"error": "Укажите инструмент"}), 400
    try:
        cache_key = f"analyze:{market or 'auto'}:{source or 'def'}:{pair.upper()}"
        if request.args.get("refresh"):
            invalidate(cache_key)
        analysis = get_cached(
            cache_key,
            lambda: analyze_pair(pair, market=market, source=source),
        )
        preview = calculate_position(
            analysis,
            PositionInput(
                entry_price=analysis.price,
                margin_usdt=100,
                leverage=10,
                side="long",
            ),
        )
        short_preview = calculate_position(
            analysis,
            PositionInput(
                entry_price=analysis.price,
                margin_usdt=100,
                leverage=10,
                side="short",
            ),
        )
        return jsonify(
            {
                "ok": True,
                "data": analysis_to_dict(analysis, pair=pair),
                "text": format_analysis(analysis),
                "tv_symbol": to_tradingview_symbol(pair, analysis.market_type),
                "position_preview": {
                    "long": position_to_dict(preview),
                    "short": position_to_dict(short_preview),
                },
            }
        )
    except MarketDataError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка загрузки: {e}"}), 500


@app.route("/api/position", methods=["GET", "POST"])
@rate_limit(40, 60)
def api_position():
    data = request.get_json(silent=True) or {}
    pair = (data.get("pair") or request.args.get("pair", "")).strip()
    market = (data.get("market") or request.args.get("market", "")).strip().lower() or None
    if market and market not in ("crypto", "stock", "forex"):
        market = None
    source = (data.get("source") or request.args.get("source", "")).strip().lower()
    source = "bybit" if source == "bybit" else None
    try:
        entry = float(data.get("entry") or request.args.get("entry", 0))
        margin = float(data.get("margin") or request.args.get("margin", 0))
        leverage = int(data.get("leverage") or request.args.get("leverage", 1))
        side = (data.get("side") or request.args.get("side", "long")).strip().lower()
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Некорректные числа в форме позиции"}), 400

    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    if entry <= 0:
        return jsonify({"ok": False, "error": "Цена входа должна быть больше 0"}), 400
    if margin <= 0:
        return jsonify({"ok": False, "error": "Сумма маржи должна быть больше 0"}), 400
    if leverage < 1:
        return jsonify({"ok": False, "error": "Плечо должно быть от 1"}), 400

    try:
        analysis = analyze_pair(pair, market=market, source=source)
        pos_input = PositionInput(
            entry_price=entry,
            margin_usdt=margin,
            leverage=leverage,
            side=side,
        )
        position = calculate_position(analysis, pos_input)
        return jsonify(
            {
                "ok": True,
                "position": position_to_dict(position),
                "text": format_position(position),
                "market_price": analysis.price,
            }
        )
    except MarketDataError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка: {e}"}), 500


@app.route("/api/bybit/account", methods=["POST"])
@rate_limit(20, 60)
def api_bybit_account():
    """READ-ONLY баланс и открытые позиции аккаунта Bybit (BYOK).

    Ключ/секрет приходят в теле запроса от браузера, используются только для
    подписи и НИГДЕ не сохраняются (ни в файлы, ни в логи). Никаких ордеров.
    """
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    secret = (data.get("secret") or "").strip()
    if not key or not secret:
        return jsonify({"ok": False, "error": "Укажите API-ключ и секрет Bybit"}), 400
    try:
        from tis.data.bybit_account import BybitAuthError, fetch_positions, fetch_wallet_balance

        balance = fetch_wallet_balance(key, secret)
        positions = fetch_positions(key, secret)
        return jsonify({"ok": True, "balance": balance, "positions": positions})
    except BybitAuthError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception:
        # Намеренно не включаем детали/ключ в текст ошибки.
        return jsonify({"ok": False, "error": "Не удалось получить данные аккаунта Bybit"}), 500


@app.route("/api/signals/scan")
@rate_limit(12, 60)
def api_signals_scan():
    """Сканер сигналов: готовые сетапы по стратегии (без исполнения сделок)."""
    market = _market_param() or "crypto"
    region = request.args.get("region", "all").strip().lower()
    if region not in ("ru", "us", "all"):
        region = "all"
    try:
        from tis.features.signal_scanner import scan_signals

        data = get_cached(f"scan:{market}:{region}", lambda: scan_signals(market, region), ttl=90)
        return jsonify({"ok": True, "market": market, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка сканера: {e}"}), 500


@app.route("/api/trainer/round")
@rate_limit(40, 60)
def api_trainer_round():
    """Раунд тренажёра: кусок реального графика (будущее скрыто) + исход.

    Инструмент анонимизирован — это чистое чтение графика (как Forex Hero).
    """
    import random
    from tis.data.instruments_catalog import CRYPTO_LIST
    from tis.data.market_data import fetch_klines
    from tis.analysis.backtester import _ema, _rsi, _atr

    level = request.args.get("level", "medium").strip().lower()
    HORIZON = {"easy": 20, "medium": 12, "hard": 6}.get(level, 12)  # короче горизонт = сложнее
    VIS = 130
    try:
        for _ in range(4):  # пара попыток на случай пустых данных
            inst = random.choice(CRYPTO_LIST)
            interval = random.choice(["1h", "4h", "1d"])
            df = fetch_klines(inst.id, interval=interval, limit=350, market="crypto")
            if df is None or len(df) < VIS + HORIZON + 5:
                continue
            start = random.randint(0, len(df) - (VIS + HORIZON))
            win = df.iloc[start:start + VIS + HORIZON]
            vis = win.iloc[:VIS]
            fut = win.iloc[VIS:]

            def _c(rows):
                out = []
                for _, r in rows.iterrows():
                    out.append({
                        "time": int(r["open_time"].timestamp()),
                        "open": round(float(r["open"]), 6), "high": round(float(r["high"]), 6),
                        "low": round(float(r["low"]), 6), "close": round(float(r["close"]), 6),
                    })
                return out

            vc, fc = _c(vis), _c(fut)
            if len(vc) < VIS or len(fc) < HORIZON:
                continue
            p0 = vc[-1]["close"]
            p1 = fc[-1]["close"]
            # Флэт — если движение за горизонт меньше ~0.75 ATR (никуда не пошло).
            try:
                atr = float(_atr(vis).iloc[-1])
            except Exception:
                atr = abs(p1 - p0)
            move = p1 - p0
            if atr > 0 and abs(move) < 0.75 * atr:
                direction = "flat"
            else:
                direction = "up" if move >= 0 else "down"
            # Подсказки «почему» — по видимому графику (для объяснения после ответа).
            hints = {}
            try:
                closes = vis["close"].astype(float)
                e20 = float(_ema(closes, 20).iloc[-1])
                e50 = float(_ema(closes, 50).iloc[-1])
                hints["trend"] = "up" if e20 > e50 * 1.001 else "down" if e20 < e50 * 0.999 else "flat"
                hints["rsi"] = round(float(_rsi(closes).iloc[-1]), 0)
                last3 = vc[-3:]
                hints["bull3"] = sum(1 for c in last3 if c["close"] >= c["open"])
            except Exception:
                hints = {}
            return jsonify({
                "ok": True, "interval": interval, "horizon": HORIZON, "level": level,
                "visible": vc, "future": fc, "hints": hints,
                "outcome": {"direction": direction, "change_pct": round((p1 - p0) / p0 * 100, 2)},
            })
        return jsonify({"ok": False, "error": "Нет данных для раунда, попробуйте ещё раз"}), 503
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка тренажёра: {e}"}), 500


@app.route("/api/paper-bot")
@rate_limit(60, 60)
def api_paper_bot():
    """Состояние серверного бумажного бота (виртуальная торговля, без ключей)."""
    try:
        from tis.features.paper_bot import ensure_running, get_state

        ensure_running()
        return jsonify({"ok": True, **get_state()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/backtest")
@rate_limit(20, 60)
def api_backtest():
    """Бэктест стратегии TIS по истории (без реальных сделок) — статистика и кривая."""
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    interval = request.args.get("interval", "1h")
    try:
        limit = min(int(request.args.get("limit", 1000)), 1000)
    except ValueError:
        limit = 1000
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    flt = _bt_filters()
    try:
        from tis.analysis.backtester import backtest
        from tis.data.market_data import fetch_klines

        fkey = f"{int(flt['use_ema200'])}{int(flt['adx_min'])}{int(flt['use_macd'])}"
        key = f"backtest:{market or 'auto'}:{interval}:{limit}:{fkey}:{pair.upper()}"
        result = get_cached(
            key,
            lambda: backtest(fetch_klines(pair, interval=interval, limit=limit, market=market), **flt),
            ttl=600,
        )
        return jsonify({"ok": True, "interval": interval, "bars": limit, "result": result})
    except MarketDataError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка бэктеста: {e}"}), 500


@app.route("/api/backtest/scan")
@rate_limit(8, 60)
def api_backtest_scan():
    """Бэктест стратегии по нескольким инструментам — таблица устойчивости."""
    market = _market_param() or "crypto"
    region = request.args.get("region", "all").strip().lower()
    if region not in ("ru", "us", "all"):
        region = "all"
    interval = request.args.get("interval", "4h")
    flt = _bt_filters()
    try:
        from tis.analysis.backtester import backtest_universe

        fkey = f"{int(flt['use_ema200'])}{int(flt['adx_min'])}{int(flt['use_macd'])}"
        data = get_cached(
            f"btscan:{market}:{region}:{interval}:{fkey}",
            lambda: backtest_universe(market, region, interval, filters=flt),
            ttl=600,
        )
        return jsonify({"ok": True, "market": market, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка сравнения: {e}"}), 500


@app.route("/api/quality")
@rate_limit(30, 60)
def api_quality():
    """Скоринг качества «по Баффету» + крупные держатели (акции, через yfinance)."""
    pair = request.args.get("pair", "").strip()
    market = _market_param() or "stock"
    lang = _lang_param()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    if market != "stock":
        return jsonify({"ok": True, "scorecard": {"available": False}, "holders": {"available": False}})
    try:
        from tis.features.fundamentals_provider import fetch_quality_scorecard, fetch_top_holders

        sc = get_cached(f"quality:{lang}:{pair.upper()}", lambda: fetch_quality_scorecard(pair, "stock", lang), ttl=3600)
        hl = get_cached(f"holders:{pair.upper()}", lambda: fetch_top_holders(pair, "stock"), ttl=21600)
        return jsonify({"ok": True, "scorecard": sc, "holders": hl})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось получить данные качества: {e}"}), 500


@app.route("/api/bybit/sentiment")
@rate_limit(40, 60)
def api_bybit_sentiment():
    """Сентимент Bybit (публичный, без ключа): Long/Short ratio + дисбаланс стакана.

    Деривативные данные (L/S ratio) в части регионов отдают 403 → тогда null.
    """
    pair = request.args.get("pair", "").strip()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    m = detect_market(pair, "crypto")
    if m != "crypto":
        return jsonify({"ok": True, "long_short": None, "orderbook": None})
    try:
        sym, _ = normalize_pair(pair, m)
        from tis.data.bybit_provider import fetch_long_short_ratio, fetch_orderbook_imbalance

        ls = get_cached(f"bbls:{sym}", lambda: fetch_long_short_ratio(sym), ttl=120)
        ob = get_cached(f"bbob:{sym}", lambda: fetch_orderbook_imbalance(sym), ttl=30)
        return jsonify({"ok": True, "symbol": sym, "long_short": ls, "orderbook": ob})
    except Exception:
        return jsonify({"ok": True, "long_short": None, "orderbook": None})


@app.route("/api/klines")
@rate_limit(90, 60)
def api_klines():
    pair = request.args.get("pair", "").strip()
    interval = request.args.get("interval", "1h")
    limit = min(int(request.args.get("limit", 200)), 500)
    market = _market_param()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    try:
        m = detect_market(pair, market)
        symbol, display = normalize_pair(pair, m)
        df = fetch_klines(pair, interval=interval, limit=limit, market=m)
        candles = []
        for _, row in df.iterrows():
            vol = row["volume"]
            candles.append(
                {
                    "time": int(row["open_time"].timestamp()),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(vol) if vol == vol else 0.0,
                }
            )
        return jsonify(
            {
                "ok": True,
                "candles": candles,
                "symbol": symbol,
                "display": display,
                "market": m,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/funding-history")
def api_funding_history():
    pair = request.args.get("pair", "").strip()
    limit = min(int(request.args.get("limit", 90)), 200)
    market = _market_param()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите пару"}), 400
    try:
        m = detect_market(pair, market)
        if m != "crypto":
            return jsonify({"ok": True, "points": [], "symbol": pair, "market": m})
        symbol, _ = normalize_pair(pair, m)
        points = fetch_funding_history(pair, limit=limit, market=m)
        return jsonify({"ok": True, "points": points, "symbol": symbol, "market": m})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


_NEWS_SPANS = {"day": 86400, "week": 7 * 86400, "month": 30 * 86400}


@app.route("/api/news")
@rate_limit(30, 60)
def api_news():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    lang = _lang_param()
    rng = request.args.get("range", "week").strip().lower()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    try:
        from tis.features.news_provider import build_query, fetch_news

        m = detect_market(pair, market)
        query = build_query(pair, m, lang)
        items = get_cached(
            f"news:{m}:{lang}:{pair.upper()}",
            lambda: fetch_news(query, 60, lang),
            ttl=300,
        )
        span = _NEWS_SPANS.get(rng, _NEWS_SPANS["week"])
        now = time.time()
        filt = [n for n in items if n["timestamp"] and (now - n["timestamp"]) <= span]
        counts = {
            "good": sum(1 for n in filt if n["sentiment"] == "good"),
            "bad": sum(1 for n in filt if n["sentiment"] == "bad"),
            "total": len(filt),
        }
        return jsonify({"ok": True, "items": filt[:40], "query": query, "range": rng, "counts": counts})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось загрузить новости: {e}"}), 500


@app.route("/api/news-ai", methods=["GET", "POST"])
@rate_limit(10, 60)
def api_news_ai():
    body = request.get_json(silent=True) or {}
    pair = (body.get("pair") or request.args.get("pair", "")).strip()
    market = _market_param()
    lang = _lang_param()
    rng = (body.get("range") or request.args.get("range", "week")).strip().lower()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400

    # Ключ пользователя (BYOK) имеет приоритет над серверным окружением.
    ai_key = (body.get("ai_key") or "").strip() or None
    ai_base = (body.get("ai_base") or "").strip() or None
    ai_model = (body.get("ai_model") or "").strip() or None

    from tis.ai.ai_news import AINewsError, analyze_news, is_configured

    if not ai_key and not is_configured():
        return jsonify(
            {
                "ok": False,
                "need_key": True,
                "error": "AI-анализ не настроен: нажмите «🔑 AI-ключ» и вставьте свой бесплатный ключ (Groq/Gemini).",
            }
        ), 200

    try:
        from tis.data.instruments_catalog import get_instrument
        from tis.features.news_provider import build_query, fetch_news

        m = detect_market(pair, market)
        items = get_cached(
            f"news:{m}:{lang}:{pair.upper()}",
            lambda: fetch_news(build_query(pair, m, lang), 60, lang),
            ttl=300,
        )
        span = _NEWS_SPANS.get(rng, _NEWS_SPANS["week"])
        now = time.time()
        filt = [n for n in items if n["timestamp"] and (now - n["timestamp"]) <= span]
        if not filt:
            return jsonify({"ok": False, "error": "Нет новостей за период для анализа"}), 200

        inst = get_instrument(pair, m)
        name = inst.name if inst else pair
        # Кэш-ключ варьируем по модели (но НЕ по секретному ключу).
        cache_tag = (ai_model or ai_base or "env")
        result = get_cached(
            f"newsai:{m}:{lang}:{pair.upper()}:{rng}:{cache_tag}",
            lambda: analyze_news(name, m, filt, lang=lang, api_key=ai_key, base_url=ai_base, model=ai_model),
            ttl=600,
        )
        return jsonify({"ok": True, "ai": result, "range": rng})
    except AINewsError as e:
        return jsonify({"ok": False, "error": str(e)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка AI-анализа: {e}"}), 500


@app.route("/api/ai-persona", methods=["POST"])
@rate_limit(15, 60)
def api_ai_persona():
    body = request.get_json(silent=True) or {}
    pair = (body.get("pair") or "").strip()
    market = (body.get("market") or "").strip().lower() or None
    if market not in ("crypto", "stock", "forex"):
        market = None
    lang = "en" if (body.get("lang") or "ru").lower() == "en" else "ru"
    persona_id = (body.get("persona") or "").strip()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400

    ai_key = (body.get("ai_key") or "").strip() or None
    ai_base = (body.get("ai_base") or "").strip() or None
    ai_model = (body.get("ai_model") or "").strip() or None

    from tis.ai.ai_personas import PersonaError, analyze_persona, build_snapshot
    from tis.ai.ai_news import is_configured

    if not ai_key and not is_configured():
        return jsonify({
            "ok": False, "need_key": True,
            "error": "AI не настроен: нажмите «🔑 AI-ключ» и вставьте свой бесплатный ключ.",
        }), 200

    try:
        cache_key = f"analyze:{market or 'auto'}:{pair.upper()}"
        analysis = get_cached(cache_key, lambda: analyze_pair(pair, market=market))
        snapshot = build_snapshot(analysis_to_dict(analysis, pair=pair), lang)
        # Персонам стоимости/роста добавляем фундаментал акции (P/E, маржа, рост).
        if persona_id in ("value", "growth", "deepvalue") and detect_market(pair, market) == "stock":
            try:
                from tis.features.fundamentals_provider import fundamentals_line
                fl = get_cached(
                    f"fundline:{lang}:{pair.upper()}",
                    lambda: fundamentals_line(pair, "stock", lang),
                    ttl=3600,
                )
                if fl:
                    snapshot += ("\nFundamentals: " if lang == "en" else "\nФундаментал: ") + fl
            except Exception:
                pass
        # Персоне «Макро» добавляем реальный макро-фон из FRED (если настроен).
        if persona_id == "macro":
            try:
                from tis.features.fred_provider import is_configured as _fred_ok, macro_line
                fred_key = (body.get("fred_key") or "").strip() or None
                if fred_key or _fred_ok():
                    tag = "env" if not fred_key else fred_key[:6]
                    ml = get_cached(f"macroline:{lang}:{tag}", lambda: macro_line(lang, fred_key), ttl=3600)
                    if ml:
                        snapshot += ("\nMacro backdrop: " if lang == "en" else "\nМакро-фон: ") + ml
            except Exception:
                pass
        tag = ai_model or ai_base or "env"
        result = get_cached(
            f"persona:{persona_id}:{lang}:{pair.upper()}:{tag}",
            lambda: analyze_persona(persona_id, snapshot, lang, api_key=ai_key, base_url=ai_base, model=ai_model),
            ttl=600,
        )
        return jsonify({"ok": True, "persona": result})
    except MarketDataError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except PersonaError as e:
        return jsonify({"ok": False, "error": str(e)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка AI-персоны: {e}"}), 500


def _format_profile(profile, lang: str) -> str:
    """Торговый профиль пользователя → текст для промпта AI-аналитика."""
    if not isinstance(profile, dict):
        return ""
    style = str(profile.get("style", "any"))
    sides = str(profile.get("sides", "both"))
    try:
        min_score = float(profile.get("minScore", 0))
        min_rr = float(profile.get("minRR", 0))
        risk = float(profile.get("riskPct", 0))
    except (TypeError, ValueError):
        min_score = min_rr = risk = 0
    flags = []
    if profile.get("requireHtf"):
        flags.append("только по тренду старших ТФ" if lang != "en" else "only with HTF trend")
    if profile.get("requireSmc"):
        flags.append("требуется подтверждение SMC" if lang != "en" else "require SMC confluence")
    if profile.get("noFlat"):
        flags.append("не входить во флэте" if lang != "en" else "skip flat market")
    sides_ru = {"both": "лонг и шорт", "long": "только лонг", "short": "только шорт"}.get(sides, sides)
    sides_en = {"both": "long & short", "long": "long only", "short": "short only"}.get(sides, sides)
    if lang == "en":
        head = "\n\nUSER TRADING RULES (judge if this setup fits, reflect it in action/plan):"
        body = (
            f"\n- style: {style}; directions: {sides_en}; min consistency score: {min_score:g};"
            f" min R:R: 1:{min_rr:g}; risk per trade: {risk:g}%."
        )
    else:
        head = "\n\nПРАВИЛА ПОЛЬЗОВАТЕЛЯ (оцени, подходит ли сетап под них, отрази в action/plan):"
        body = (
            f"\n- стиль: {style}; направления: {sides_ru}; мин. балл согласованности: {min_score:g};"
            f" мин. R:R: 1:{min_rr:g}; риск на сделку: {risk:g}%."
        )
    if flags:
        body += "\n- " + "; ".join(flags) + "."
    return head + body


@app.route("/api/ai-analyst", methods=["POST"])
@rate_limit(15, 60)
def api_ai_analyst():
    """AI-аналитик: ИИ-заключение по нашему анализу (+ данные Bybit на full)."""
    body = request.get_json(silent=True) or {}
    pair = (body.get("pair") or "").strip()
    market = (body.get("market") or "").strip().lower() or None
    if market not in ("crypto", "stock", "forex"):
        market = None
    source = (body.get("source") or "").strip().lower()
    source = "bybit" if source == "bybit" else None
    lang = "en" if (body.get("lang") or "ru").lower() == "en" else "ru"
    level = "simple" if (body.get("level") or "full").lower() == "simple" else "full"
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400

    ai_key = (body.get("ai_key") or "").strip() or None
    ai_base = (body.get("ai_base") or "").strip() or None
    ai_model = (body.get("ai_model") or "").strip() or None

    from tis.ai.ai_analyst import AnalystError, analyze_market, build_analyst_snapshot
    from tis.ai.ai_news import is_configured

    if not ai_key and not is_configured():
        return jsonify({
            "ok": False, "need_key": True,
            "error": "AI не настроен: нажмите «🔑 AI-ключ» и вставьте свой бесплатный ключ.",
        }), 200

    # Открытые позиции пользователя на этом инструменте (если переданы фронтом).
    positions = body.get("positions") if isinstance(body.get("positions"), list) else None
    if positions:
        sym = pair.replace("/", "").upper()
        positions = [p for p in positions if str(p.get("symbol", "")).upper().startswith(sym[:6])][:3]

    try:
        cache_key = f"analyze:{market or 'auto'}:{source or 'def'}:{pair.upper()}"
        analysis = get_cached(cache_key, lambda: analyze_pair(pair, market=market, source=source))
        snapshot = build_analyst_snapshot(
            analysis_to_dict(analysis, pair=pair), lang, level, source, positions
        )
        # Личные правила пользователя (торговый профиль) — ИИ оценивает сетап под них.
        prof_txt = _format_profile(body.get("profile"), lang)
        if prof_txt:
            snapshot += prof_txt
        has_pos = bool(positions)
        result = analyze_market(
            snapshot, lang, level, has_pos,
            api_key=ai_key, base_url=ai_base, model=ai_model,
        )
        return jsonify({"ok": True, "analyst": result})
    except MarketDataError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except AnalystError as e:
        return jsonify({"ok": False, "error": str(e)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка AI-аналитика: {e}"}), 500


@app.route("/api/macro", methods=["GET", "POST"])
@rate_limit(30, 60)
def api_macro():
    lang = _lang_param()
    body = request.get_json(silent=True) or {}
    user_key = (body.get("fred_key") or request.args.get("fred_key") or "").strip() or None
    from tis.features.fred_provider import fetch_macro, is_configured

    if not user_key and not is_configured():
        return jsonify({
            "ok": False, "need_key": True,
            "error": "Макро-данные не настроены: вставьте бесплатный ключ FRED ниже "
                     "(fred.stlouisfed.org/docs/api/api_key.html).",
        }), 200
    try:
        # Кэш по языку + по ключу (данные публичные, но ключ влияет на источник).
        tag = "env" if not user_key else user_key[:6]
        data = get_cached(f"macro:{lang}:{tag}", lambda: fetch_macro(lang, user_key), ttl=3600)
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось загрузить макро (проверьте ключ): {e}"}), 500


_MOVERS_TTL = {"day": 90, "month": 1800, "year": 3600}


@app.route("/api/movers")
@rate_limit(20, 60)
def api_movers():
    market = _market_param() or "crypto"
    rng = request.args.get("range", "day").strip().lower()
    if rng not in ("day", "month", "year"):
        rng = "day"
    region = request.args.get("region", "all").strip().lower()
    if region not in ("ru", "us", "all"):
        region = "all"
    try:
        from tis.features.movers_provider import fetch_movers

        data = get_cached(
            f"movers:{market}:{region}:{rng}",
            lambda: fetch_movers(market, rng, region),
            ttl=_MOVERS_TTL.get(rng, 300),
        )
        return jsonify({"ok": True, "market": market, "range": rng, "region": region, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось загрузить движения: {e}"}), 500


@app.route("/api/strip-quotes")
@rate_limit(40, 60)
def api_strip_quotes():
    """Цена/изменение/спарклайн для видимых карточек верхней полосы (батч, кэш 60с)."""
    market = _market_param() or "crypto"
    ids = [x.strip() for x in request.args.get("ids", "").split(",") if x.strip()][:16]
    if not ids:
        return jsonify({"ok": True, "quotes": {}})
    try:
        from tis.features.movers_provider import strip_quotes

        key = f"strip:{market}:" + ",".join(sorted(ids))
        data = get_cached(key, lambda: strip_quotes(market, ids), ttl=60)
        return jsonify({"ok": True, "quotes": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/correlations")
@rate_limit(20, 60)
def api_correlations():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    region = request.args.get("region", "all").strip().lower()
    if region not in ("ru", "us", "all"):
        region = "all"
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    try:
        from tis.features.correlation_provider import correlations

        m = detect_market(pair, market)
        data = get_cached(
            f"corr:{m}:{region}:{pair.upper()}",
            lambda: correlations(pair, m, region),
            ttl=1800,
        )
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось посчитать корреляции: {e}"}), 500


@app.route("/api/quote")
@rate_limit(120, 60)
def api_quote():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    try:
        m = detect_market(pair, market)
        t = get_cached(f"quote:{m}:{pair.upper()}", lambda: fetch_ticker_24h(pair, m), ttl=60)
        return jsonify({
            "ok": True, "pair": pair, "market": m,
            "price": float(t.get("lastPrice", 0)),
            "change_pct": round(float(t.get("priceChangePercent", 0)), 2),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/portfolio-risk", methods=["POST"])
@rate_limit(20, 60)
def api_portfolio_risk():
    body = request.get_json(silent=True) or {}
    holdings = body.get("holdings") or []
    if not isinstance(holdings, list):
        return jsonify({"ok": False, "error": "Неверный формат портфеля"}), 400
    try:
        from tis.features.portfolio_provider import portfolio_risk

        data = portfolio_risk(holdings)
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось посчитать риск: {e}"}), 500


@app.route("/api/fundamentals")
@rate_limit(30, 60)
def api_fundamentals():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    lang = _lang_param()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    try:
        from tis.features.fundamentals_provider import fetch_fundamentals

        m = detect_market(pair, market)
        data = get_cached(
            f"fund:{m}:{lang}:{pair.upper()}",
            lambda: fetch_fundamentals(pair, m, lang),
            ttl=3600,
        )
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось загрузить фундаментал: {e}"}), 500


@app.route("/api/dividends")
@rate_limit(30, 60)
def api_dividends():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    try:
        from tis.features.fundamentals_provider import fetch_dividend_info

        m = detect_market(pair, market)
        data = get_cached(
            f"div:{m}:{pair.upper()}",
            lambda: fetch_dividend_info(pair, m),
            ttl=1800,
        )
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось загрузить дивиденды: {e}"}), 500


@app.route("/api/screener")
@rate_limit(15, 60)
def api_screener():
    market = _market_param() or "crypto"
    region = request.args.get("region", "all").strip().lower()
    if region not in ("ru", "us", "all"):
        region = "all"
    tf = request.args.get("tf", "1d").strip().lower()
    try:
        from tis.features.screener_provider import screen_market

        data = get_cached(
            f"screener:{market}:{region}:{tf}",
            lambda: screen_market(market, region, tf),
            ttl=300,
        )
        return jsonify({"ok": True, "market": market, "region": region, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось загрузить скринер: {e}"}), 500


# Журнал сигналов хранится на КЛИЕНТЕ (localStorage). Сервер только: валидирует
# запись при добавлении и stateless-оценивает исходы по истории цены. Никакого
# общего файла — нет утечки данных между пользователями (см. signal_journal).

@app.route("/api/journal/add", methods=["POST"])
def api_journal_add():
    from tis.features import signal_journal

    data = request.get_json(silent=True) or {}
    try:
        record = signal_journal.build_record(data)  # валидирует, НЕ сохраняет
        return jsonify({"ok": True, "signal": record})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось записать сигнал: {e}"}), 500


@app.route("/api/journal/evaluate", methods=["POST"])
def api_journal_evaluate():
    from tis.features import signal_journal

    data = request.get_json(silent=True) or {}
    signals = data.get("signals") or []
    try:
        result = signal_journal.evaluate(signals, fetch_klines)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка оценки журнала: {e}"}), 500


def _port_in_use(host: str, port: int) -> bool:
    """Занят ли порт. Проверяем по 127.0.0.1, если host=0.0.0.0 (он не коннектится)."""
    import socket

    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((probe_host, port)) == 0


def _safe_open_browser(host: str, port: int) -> None:
    open_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    try:
        webbrowser.open(f"http://{open_host}:{port}")
    except Exception:
        pass  # нет браузера/headless — не критично, сервер уже поднят


def run_server(host: str = "127.0.0.1", port: int = 5000, open_browser: bool = True) -> None:
    # Если порт уже занят — почти наверняка работает СТАРЫЙ экземпляр сервера
    # (он будет отдавать устаревшую страницу). Падаем с понятным сообщением,
    # а не с сырым OSError, чтобы было ясно, что делать.
    if _port_in_use(host, port):
        print(
            f"\n  ⚠ Порт {port} уже занят — вероятно, старый сервер ещё работает.\n"
            f"    Закройте его (Ctrl+C в том окне) или завершите процесс на порту {port},\n"
            f"    иначе в браузере будет открываться УСТАРЕВШАЯ версия страницы.\n"
            f"    Windows:  Get-NetTCPConnection -LocalPort {port} | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force }}\n",
            flush=True,
        )
        raise SystemExit(1)
    if open_browser:
        Timer(1.2, lambda: _safe_open_browser(host, port)).start()
    print(f"\n  Торговый помощник: http://{host}:{port}\n", flush=True)
    # threaded=True обязателен: фронт (SPA) шлёт много параллельных запросов
    # (live-поллинг + анализ + котировки). Без потоков один долгий cold-analyze
    # блокирует весь сервер, и в браузере всё «зависает».
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    import os
    import sys

    # Консоль Windows по умолчанию cp1251/866 → кириллица и эмодзи в print
    # роняют процесс UnicodeEncodeError. Переводим вывод в UTF-8 (errors=replace).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    port = int(os.environ.get("PORT", 5000))
    local = os.environ.get("PORT") is None
    run_server(host="0.0.0.0" if not local else "127.0.0.1", port=port, open_browser=local)
