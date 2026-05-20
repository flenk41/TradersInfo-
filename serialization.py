"""Сериализация анализа в JSON для веб-интерфейса."""

from __future__ import annotations

from dataclasses import asdict

from analyzer import MarketAnalysis
from position_calculator import PositionResult


def analysis_to_dict(analysis: MarketAnalysis) -> dict:
    return asdict(analysis)


def position_to_dict(position: PositionResult) -> dict:
    return asdict(position)
