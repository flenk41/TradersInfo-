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

from instruments_catalog import catalog_for_frontend, list_instruments
from data_cache import get_cached, invalidate
from engine import analyze_pair
from formatter import format_analysis, format_position
from market_data import fetch_funding_history, fetch_klines
from markets import MarketDataError, detect_market, normalize_pair, to_tradingview_symbol
from position_calculator import PositionInput, calculate_position
from serialization import analysis_to_dict, position_to_dict

app = Flask(__name__, template_folder="templates", static_folder="static")

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

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
        from universe import search_universe

        items = search_universe(market, region, q)
        return jsonify({"ok": True, "items": items, "count": len(items)})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Поиск недоступен: {e}"}), 500


def _market_param() -> str | None:
    m = request.args.get("market", "").strip().lower()
    return m if m in ("crypto", "stock", "forex") else None


def _lang_param() -> str:
    return "en" if request.args.get("lang", "ru").strip().lower() == "en" else "ru"


@app.route("/api/analyze")
@rate_limit(30, 60)
def api_analyze():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    if not pair:
        return jsonify({"error": "Укажите инструмент"}), 400
    try:
        cache_key = f"analyze:{market or 'auto'}:{pair.upper()}"
        if request.args.get("refresh"):
            invalidate(cache_key)
        analysis = get_cached(
            cache_key,
            lambda: analyze_pair(pair, market=market),
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
        analysis = analyze_pair(pair, market=market)
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
        from news_provider import build_query, fetch_news

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


@app.route("/api/news-ai")
@rate_limit(10, 60)
def api_news_ai():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    lang = _lang_param()
    rng = request.args.get("range", "week").strip().lower()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400

    from ai_news import AINewsError, analyze_news, is_configured

    if not is_configured():
        return jsonify(
            {
                "ok": False,
                "need_key": True,
                "error": "AI-анализ не настроен: добавьте OPENAI_API_KEY в файл .env и перезапустите сервер.",
            }
        ), 200

    try:
        from instruments_catalog import get_instrument
        from news_provider import build_query, fetch_news

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
        result = get_cached(
            f"newsai:{m}:{lang}:{pair.upper()}:{rng}",
            lambda: analyze_news(name, m, filt, lang=lang),
            ttl=600,
        )
        return jsonify({"ok": True, "ai": result, "range": rng})
    except AINewsError as e:
        return jsonify({"ok": False, "error": str(e)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка AI-анализа: {e}"}), 500


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
        from movers_provider import fetch_movers

        data = get_cached(
            f"movers:{market}:{region}:{rng}",
            lambda: fetch_movers(market, rng, region),
            ttl=_MOVERS_TTL.get(rng, 300),
        )
        return jsonify({"ok": True, "market": market, "range": rng, "region": region, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось загрузить движения: {e}"}), 500


@app.route("/api/journal", methods=["GET"])
def api_journal():
    import signal_journal

    try:
        data = signal_journal.get_journal(fetch_klines)
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка журнала: {e}"}), 500


@app.route("/api/journal/add", methods=["POST"])
def api_journal_add():
    import signal_journal

    data = request.get_json(silent=True) or {}
    try:
        record = signal_journal.add_signal(data)
        return jsonify({"ok": True, "signal": record})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не удалось записать сигнал: {e}"}), 500


@app.route("/api/journal/delete", methods=["POST"])
def api_journal_delete():
    import signal_journal

    data = request.get_json(silent=True) or {}
    sid = (data.get("id") or "").strip()
    if data.get("all"):
        signal_journal.clear_all()
        return jsonify({"ok": True})
    if not sid:
        return jsonify({"ok": False, "error": "Укажите id сигнала"}), 400
    ok = signal_journal.delete_signal(sid)
    return jsonify({"ok": ok})


def run_server(host: str = "127.0.0.1", port: int = 5000, open_browser: bool = True) -> None:
    if open_browser:
        Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    print(f"\n  Торговый помощник: http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5000))
    local = os.environ.get("PORT") is None
    run_server(host="0.0.0.0" if not local else "127.0.0.1", port=port, open_browser=local)
