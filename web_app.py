"""Веб-интерфейс с кнопками для торгового помощника."""

from __future__ import annotations

import json
import time
import webbrowser
from threading import Timer

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
from risk_manager import RiskInput, calculate_risk_plan
from serialization import analysis_to_dict, position_to_dict, risk_to_dict

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def index():
    return render_template(
        "index.html",
        instrument_catalog=json.dumps(catalog_for_frontend(), ensure_ascii=False),
    )


@app.route("/api/instruments")
def api_instruments():
    market = request.args.get("market", "crypto").strip().lower()
    region = request.args.get("region", "all").strip().lower()
    if market not in ("crypto", "stock", "forex"):
        return jsonify({"ok": False, "error": "Неверный рынок"}), 400
    return jsonify({"ok": True, "items": list_instruments(market, region)})


def _market_param() -> str | None:
    m = request.args.get("market", "").strip().lower()
    return m if m in ("crypto", "stock", "forex") else None


@app.route("/api/analyze")
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


@app.route("/api/risk", methods=["GET", "POST"])
def api_risk():
    data = request.get_json(silent=True) or {}
    pair = (data.get("pair") or request.args.get("pair", "")).strip()
    market = (data.get("market") or request.args.get("market", "")).strip().lower() or None
    if market and market not in ("crypto", "stock", "forex"):
        market = None

    def _float(key, default=0.0):
        v = data.get(key) if key in data else request.args.get(key)
        return float(v) if v not in (None, "") else default

    def _int(key, default=None):
        v = data.get(key) if key in data else request.args.get(key)
        return int(v) if v not in (None, "") else default

    try:
        balance = _float("balance")
        entry = _float("entry")
        stop = _float("stop")
        risk_pct = _float("risk_pct", 1.0)
        max_daily = _float("max_daily_pct", 3.0)
        max_portfolio = _float("max_portfolio_pct", 6.0)
        daily_used = _float("daily_loss_used_pct", 0.0)
        open_trades = _int("open_trades", 0) or 0
        leverage = _int("leverage")
        margin = _float("margin") if (data.get("margin") or request.args.get("margin")) else None
        tp_raw = data.get("take_profit") or request.args.get("take_profit")
        take_profit = float(tp_raw) if tp_raw not in (None, "") else None
        side = (data.get("side") or request.args.get("side", "long")).strip().lower()
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Некорректные параметры риска"}), 400

    if balance <= 0:
        return jsonify({"ok": False, "error": "Укажите размер депозита"}), 400
    if entry <= 0 or stop <= 0:
        return jsonify({"ok": False, "error": "Укажите цену входа и стоп"}), 400

    analysis = None
    if pair and take_profit is None:
        try:
            cache_key = f"analyze:{market or 'auto'}:{pair.upper()}"
            analysis = get_cached(
                cache_key,
                lambda: analyze_pair(pair, market=market),
            )
            calc = calculate_position(
                analysis,
                PositionInput(
                    entry_price=entry,
                    margin_usdt=margin or 100,
                    leverage=leverage or 10,
                    side=side,
                ),
            )
            take_profit = calc.take_profit
        except MarketDataError:
            pass

    try:
        plan = calculate_risk_plan(
            RiskInput(
                balance_usdt=balance,
                risk_per_trade_pct=risk_pct,
                max_daily_loss_pct=max_daily,
                max_portfolio_risk_pct=max_portfolio,
                entry=entry,
                stop=stop,
                take_profit=take_profit,
                side=side,
                leverage=leverage,
                margin_usdt=margin,
                daily_loss_used_pct=daily_used,
                open_trades=open_trades,
            ),
            analysis=analysis,
        )
        return jsonify({"ok": True, "risk": risk_to_dict(plan)})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка: {e}"}), 500


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
def api_news():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
    rng = request.args.get("range", "week").strip().lower()
    if not pair:
        return jsonify({"ok": False, "error": "Укажите инструмент"}), 400
    try:
        from news_provider import build_query, fetch_news

        m = detect_market(pair, market)
        query = build_query(pair, m)
        items = get_cached(
            f"news:{m}:{pair.upper()}",
            lambda: fetch_news(query, 60),
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
def api_news_ai():
    pair = request.args.get("pair", "").strip()
    market = _market_param()
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
            f"news:{m}:{pair.upper()}",
            lambda: fetch_news(build_query(pair, m), 60),
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
            f"newsai:{m}:{pair.upper()}:{rng}",
            lambda: analyze_news(name, m, filt),
            ttl=600,
        )
        return jsonify({"ok": True, "ai": result, "range": rng})
    except AINewsError as e:
        return jsonify({"ok": False, "error": str(e)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка AI-анализа: {e}"}), 500


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
