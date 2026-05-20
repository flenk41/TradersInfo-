"""Веб-интерфейс с кнопками для торгового помощника."""

from __future__ import annotations

import webbrowser
from threading import Timer

from flask import Flask, jsonify, render_template, request

from config import POPULAR_PAIRS
from data_fetcher import BinanceDataError
from engine import analyze_pair
from formatter import format_analysis, format_position
from position_calculator import PositionInput, calculate_position
from serialization import analysis_to_dict, position_to_dict

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def index():
    return render_template("index.html", pairs=POPULAR_PAIRS)


@app.route("/api/analyze")
def api_analyze():
    pair = request.args.get("pair", "").strip()
    if not pair:
        return jsonify({"error": "Укажите торговую пару"}), 400
    try:
        analysis = analyze_pair(pair)
        return jsonify(
            {
                "ok": True,
                "data": analysis_to_dict(analysis),
                "text": format_analysis(analysis),
            }
        )
    except BinanceDataError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка загрузки: {e}"}), 500


@app.route("/api/position", methods=["GET", "POST"])
def api_position():
    data = request.get_json(silent=True) or {}
    pair = (data.get("pair") or request.args.get("pair", "")).strip()
    try:
        entry = float(data.get("entry") or request.args.get("entry", 0))
        margin = float(data.get("margin") or request.args.get("margin", 0))
        leverage = int(data.get("leverage") or request.args.get("leverage", 1))
        side = (data.get("side") or request.args.get("side", "long")).strip().lower()
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Некорректные числа в форме позиции"}), 400

    if not pair:
        return jsonify({"ok": False, "error": "Укажите торговую пару"}), 400
    if entry <= 0:
        return jsonify({"ok": False, "error": "Цена входа должна быть больше 0"}), 400
    if margin <= 0:
        return jsonify({"ok": False, "error": "Сумма маржи должна быть больше 0"}), 400
    if leverage < 1:
        return jsonify({"ok": False, "error": "Плечо должно быть от 1"}), 400

    try:
        analysis = analyze_pair(pair)
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
    except BinanceDataError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка: {e}"}), 500


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
