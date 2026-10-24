"""Signale: Trend aus gleitenden Durchschnitten + Nachrichtenstimmung."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .broker.base import Bar


@dataclass
class Signal:
    symbol: str
    trend: float
    news: float
    market: float
    score: float


def sma(values: list[float], n: int) -> float:
    return sum(values[-n:]) / n


def trend_score(bars: list[Bar], fast: int, slow: int) -> float:
    """-1..1: positiv, wenn kurzer Durchschnitt über langem liegt und Kurs darüber steigt."""
    closes = [b.close for b in bars]
    if len(closes) < slow + 1:
        return 0.0
    f, s = sma(closes, fast), sma(closes, slow)
    gap = (f - s) / s                          # Abstand der Durchschnitte
    momentum = closes[-1] / closes[-fast] - 1  # Kursänderung über das kurze Fenster
    return math.tanh(15 * gap + 5 * momentum)


def combine(symbol: str, trend: float, news: float, market: float, cfg) -> Signal:
    st = cfg.strategy
    score = st.trend_weight * trend + st.news_weight * news + st.market_news_weight * min(market, 0.0)
    # schlechte Weltlage bremst Käufe, gute Weltlage treibt nicht zusätzlich an
    return Signal(symbol, trend, news, market, max(-1.0, min(1.0, score)))
