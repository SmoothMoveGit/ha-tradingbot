"""Momentum-Rotation als Vergleich zur aktuellen Strategie (nur Backtest, handelt nicht).

Idee aus der Forschung zu Aktien-Momentum (Jegadeesh/Titman, "12-1"-Momentum) und Dual Momentum (Antonacci):
einmal im Monat die Aktien mit der besten Rendite der letzten 12 Monate (ohne den letzten Monat) kaufen,
gleich gewichtet. Optional nur Aktien über ihrem 200-Tage-Schnitt und ein Marktfilter: liegt der
Gesamtmarkt (SPY) unter seinem 200-Tage-Schnitt, bleibt das Geld in bar.
Jeder Tag sieht nur Kurse bis zu diesem Tag.
"""
from __future__ import annotations

from datetime import date

from .broker.base import Bar

SLIPPAGE = 0.0005  # 0,05 % pro Kauf oder Verkauf


def _closes(bars: list[Bar]) -> tuple[list[date], list[float]]:
    return [b.time.date() for b in bars], [b.close for b in bars]


def run_momentum(bars: dict[str, list[Bar]], symbols: list[str], start: date, end: date, *,
                 budget: float = 300.0, deposit: float = 55.0, top_n: int = 4, lookback: int = 252,
                 skip: int = 21, abs_filter: bool = True, regime: str | None = "SPY",
                 benchmark: str | None = "URTH") -> dict:
    series = {s: _closes(bars[s]) for s in set(symbols) | {regime, benchmark} - {None} if bars.get(s)}
    index = {s: {d: i for i, d in enumerate(ds)} for s, (ds, _) in series.items()}
    ref = benchmark if benchmark in series else regime if regime in series else symbols[0]
    days = [d for d in series[ref][0] if start <= d <= end]

    def price(s: str, d: date) -> float | None:
        i = index[s].get(d)
        return series[s][1][i] if i is not None else None

    def hist(s: str, d: date) -> list[float]:
        i = index[s].get(d)
        return series[s][1][: i + 1] if i is not None else []

    def above_sma(s: str, d: date, n: int = 200) -> bool:
        c = hist(s, d)
        return len(c) >= n and c[-1] > sum(c[-n:]) / n

    cash, held, paid, units = budget, {}, budget, 0.0
    peak, max_dd, month, trades = 1.0, 0.0, None, 0
    for d in days:
        m = d.year * 12 + d.month
        new_month = m != month
        if month is not None and new_month and deposit:
            cash += deposit
            paid += deposit
            if benchmark in series and price(benchmark, d):
                units += deposit / price(benchmark, d)
        if benchmark in series and not units and price(benchmark, d):
            units = budget / price(benchmark, d)
        month = m
        if new_month:
            pick: list[str] = []
            if not regime or regime not in series or above_sma(regime, d):
                scores = []
                for s in symbols:
                    c = hist(s, d)
                    if s not in series or len(c) < lookback + 1:
                        continue
                    score = c[-1 - skip] / c[-1 - lookback] - 1
                    if abs_filter and (score <= 0 or not above_sma(s, d)):
                        continue
                    scores.append((score, s))
                pick = [s for _, s in sorted(scores, reverse=True)[:top_n]]
            value = cash + sum(q * (price(s, d) or 0) for s, q in held.items())
            for s in list(held):  # verkaufen, was nicht mehr dabei ist
                if s not in pick and price(s, d):
                    cash += held.pop(s) * price(s, d) * (1 - SLIPPAGE)
                    trades += 1
            target = value / top_n if pick else 0.0
            for s in pick:  # auf gleiche Gewichte bringen
                p = price(s, d)
                if not p:
                    continue
                diff = target - held.get(s, 0.0) * p
                if diff < -1:
                    q = -diff / p
                    held[s] -= q
                    cash += q * p * (1 - SLIPPAGE)
                    trades += 1
                elif diff > 1:
                    amount = min(diff, cash)
                    held[s] = held.get(s, 0.0) + amount * (1 - SLIPPAGE) / p
                    cash -= amount
                    trades += 1
        equity = cash + sum(q * (price(s, d) or hist(s, d)[-1]) for s, q in held.items())
        ratio = equity / paid
        peak = max(peak, ratio)
        max_dd = max(max_dd, 1 - ratio / peak)
    final = cash + sum(q * hist(s, days[-1])[-1] for s, q in held.items())
    bench_final = units * price(benchmark, days[-1]) if benchmark in series else None
    return {"start": days[0], "end": days[-1], "paid_in": paid, "final": final, "return_pct": final / paid - 1,
            "max_drawdown_pct": max_dd, "trades": trades,
            "benchmark_return_pct": bench_final / paid - 1 if bench_final else None}


def compare_momentum(cfg, bars: dict[str, list[Bar]], start: date, cut: date, end: date,
                     sets: list[tuple[str, list[str]]]) -> list[str]:
    small, big = sets[0][1], sets[-2][1]  # aktuelle Watchlist und "Aktien ohne ETFs"
    variants = [
        (f"Top 4 aus {len(small)}, ohne Filter", small, dict(top_n=4, abs_filter=False, regime=None)),
        (f"Top 4 aus {len(small)} + Filter", small, dict(top_n=4)),
        (f"Top 4 aus {len(big)} + Filter", big, dict(top_n=4)),
        (f"Top 6 aus {len(big)} + Filter", big, dict(top_n=6)),
        (f"Top 4 aus {len(big)}, 6 Monate", big, dict(top_n=4, lookback=126)),
    ]
    base = dict(budget=cfg.risk.start_budget, deposit=cfg.risk.monthly_deposit, benchmark=cfg.benchmark)
    lines = ["MOMENTUM-ROTATION (monatlich die stärksten Aktien der letzten 12 Monate ohne letzten Monat, "
             "Filter = Aktie und Markt über 200-Tage-Schnitt)"]
    for name, syms, kw in variants:
        full = run_momentum(bars, syms, start, end, **base, **kw)
        a = run_momentum(bars, syms, start, cut, **base, **kw)
        b = run_momentum(bars, syms, cut, end, **base, **kw)
        lines.append(f"  {name:26} 3 J {full['return_pct']:+7.1%} (Rückg. {full['max_drawdown_pct']:4.0%}, "
                     f"{full['trades']:3d} Tr.) | A {a['return_pct']:+7.1%} (Rückg. {a['max_drawdown_pct']:4.0%}) "
                     f"| B {b['return_pct']:+7.1%} (Rückg. {b['max_drawdown_pct']:4.0%})")
    return lines
