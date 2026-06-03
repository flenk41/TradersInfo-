"""Сериализация анализа в JSON для веб-интерфейса."""

from __future__ import annotations

from dataclasses import asdict

from tis.analysis.analyzer import MarketAnalysis
from tis.analysis.position_calculator import PositionResult
from tis.analysis.accuracy_estimator import AccuracyMetrics
from tis.analysis.risk_manager import RiskPlan


def analysis_to_dict(analysis: MarketAnalysis, pair: str | None = None) -> dict:
    data = asdict(analysis)
    if pair:
        from tis.core.markets import to_tradingview_symbol

        data["tv_symbol"] = to_tradingview_symbol(pair, analysis.market_type)
    return data


def position_to_dict(position: PositionResult) -> dict:
    return asdict(position)


def risk_to_dict(plan: RiskPlan) -> dict:
    return asdict(plan)


def accuracy_to_dict(metrics: AccuracyMetrics) -> dict:
    return asdict(metrics)
