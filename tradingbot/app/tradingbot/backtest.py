"""Backtest: die Handelsregeln gegen echte Tageskurse der Vergangenheit laufen lassen.

Nachrichten gibt es rückwirkend nicht, der Backtest prüft also nur Trend-Signal und Risikoregeln.
Gekauft und verkauft wird jeweils zum Tagesschlusskurs.
"""
from __future__ import annotations

import bisect
import copy
import logging
from datetime import date

from .bot import TradingBot
from .config import _merge
from .broker.base import Bar
from .broker.sim import SimBroker
from .storage import Storage

log = logging.getLogger(__name__)


class HistoricalBroker(SimBroker):
    """Spielt echte Kurse Tag für Tag ab. Kein Zugriff auf Kurse aus der Zukunft."""

    def __init__(self, cash: float, bars: dict[str, list[Bar]]):
        self.cash = cash
        self.holdings = {}
        self.full = {s: sorted(b, key=lambda x: x.time) for s, b in bars.items() if b}
        self.days = {s: [x.time.date() for x in b] for s, b in self.full.items()}
        self.history = {s: [] for s in self.full}

    def set_date(self, d: date) -> None:
        for s, days in self.days.items():
            self.history[s] = self.full[s][: bisect.bisect_right(days, d)]

    def daily_bars(self, symbol: str, days: int) -> list[Bar]:
        if not self.history.get(symbol):
            raise KeyError(f"keine Kurse für {symbol}")
        return self.history[symbol][-days:]


def run_backtest(cfg, bars: dict[str, list[Bar]], start: date | None = None, end: date | None = None) -> dict:
    cfg = copy.deepcopy(cfg)
    cfg.mode = "sim"
    cfg.news.use_alpaca_news = False
    cfg.news.rss_feeds = []
    cfg.news.sentiment_engine = "lexicon"
    cfg.risk.broker_stops = False
    budget = cfg.risk.start_budget

    broker = HistoricalBroker(budget, bars)
    bot = TradingBot(cfg, broker, Storage(":memory:"))
    bench = cfg.benchmark if cfg.benchmark in broker.full else None
    calendar = broker.days[bench] if bench else sorted({d for ds in broker.days.values() for d in ds})
    days = [d for d in calendar[cfg.strategy.sma_slow + 5:] if (not start or d >= start) and (not end or d <= end)]
    if not days:
        raise ValueError("zu wenig Kursdaten für einen Backtest")

    bot_logger = logging.getLogger("tradingbot.bot")
    level = bot_logger.level
    bot_logger.setLevel(logging.WARNING)
    deposit = cfg.risk.monthly_deposit
    paid, units, peak, max_dd, month = budget, 0.0, 1.0, 0.0, None
    try:
        for d in days:
            broker.set_date(d)
            m = d.year * 12 + d.month
            if month is not None and m != month and deposit:
                broker.cash += deposit  # dieselbe Einzahlung, die der Bot in seinem Kapital bucht
                paid += deposit
                if bench:
                    units += deposit / broker.last_price(bench)
            month = m
            bot.run_cycle(today=d)
            if bench and not units:
                units = budget / broker.last_price(bench)
            ratio = broker.account().equity / paid
            peak = max(peak, ratio)
            max_dd = max(max_dd, 1 - ratio / peak)
    finally:
        bot_logger.setLevel(level)

    trades = bot.storage.recent_trades(100_000)
    sells = [t for t in trades if t[2] == "sell"]
    final = broker.account().equity
    return {
        "start": days[0], "end": days[-1], "budget": budget, "paid_in": paid, "final": final,
        "return_pct": final / paid - 1, "max_drawdown_pct": max_dd,
        "trades": len(trades), "sells": len(sells),
        "win_rate": sum(1 for t in sells if t[5] > 0) / len(sells) if sells else 0.0,
        "halted": bot.risk.halted,
        "benchmark": bench,
        "benchmark_final": units * broker.last_price(bench) if bench else None,
        "benchmark_return_pct": units * broker.last_price(bench) / paid - 1 if bench else None,
    }


def format_result(r: dict) -> list[str]:
    lines = [
        f"BACKTEST {r['start']} bis {r['end']} (nur Trend + Risikoregeln, ohne Nachrichten)",
        f"  Eingezahlt {r['paid_in']:.0f} $ (Start {r['budget']:.0f} $ + monatlich) -> Bot {r['final']:.2f} $ "
        f"({r['return_pct']:+.1%}), größter Rückgang {r['max_drawdown_pct']:.1%}",
        f"  {r['trades']} Trades, {r['sells']} Verkäufe, davon {r['win_rate']:.0%} mit Gewinn",
    ]
    if r["halted"]:
        lines.append("  Achtung: Not-Aus (max. Verlust) wurde im Testzeitraum ausgelöst, danach kein Handel mehr")
    if r["benchmark"]:
        diff = r["return_pct"] - r["benchmark_return_pct"]
        lines.append(f"  Vergleich {r['benchmark']} (gleiche Einzahlungen): {r['benchmark_final']:.2f} $ "
                     f"({r['benchmark_return_pct']:+.1%}) "
                     f"-> Bot {'besser' if diff >= 0 else 'schlechter'} um {abs(diff):.1%}-Punkte")
    return lines


# Varianten für den Vergleich. Jede ändert nur die genannten Einstellungen gegenüber der aktuellen config.
VARIANTS: list[tuple[str, dict]] = [
    ("aktuell", {}),
    ("weite Stops", {"risk": {"stop_loss_pct": 0.10, "trailing_stop_pct": 0.12, "take_profit_pct": 0.30}}),
    ("ohne Gewinnmitnahme", {"risk": {"take_profit_pct": 10.0, "trailing_stop_pct": 0.10}}),
    ("langer Trend 20/50", {"strategy": {"sma_fast": 20, "sma_slow": 50}}),
    ("langer Trend + weite Stops", {"strategy": {"sma_fast": 20, "sma_slow": 50},
                                    "risk": {"stop_loss_pct": 0.10, "trailing_stop_pct": 0.12, "take_profit_pct": 0.30}}),
    ("Trendfolger 50/200", {"strategy": {"sma_fast": 50, "sma_slow": 200, "sell_threshold": -0.1},
                            "risk": {"stop_loss_pct": 0.15, "trailing_stop_pct": 0.15, "take_profit_pct": 10.0}}),
    ("weniger Trades", {"strategy": {"buy_threshold": 0.5, "sell_threshold": -0.4},
                        "risk": {"rebuy_cooldown_days": 5}}),
    ("8 kleinere Positionen", {"risk": {"max_positions": 8, "max_position_pct": 0.11}}),
    ("nur Signal, keine Stops", {"risk": {"stop_loss_pct": 0.99, "trailing_stop_pct": 0.99, "take_profit_pct": 10.0}}),
]
# Hebel wie bei Faktor-Zertifikaten: tägliche Kursänderung mal Faktor, dazu laufende Kosten.
LEVERAGED: list[tuple[str, dict]] = [
    ("Hebel 2x, aktuell", {}),
    ("Hebel 2x, Trendfolger 50/200", dict(VARIANTS)["Trendfolger 50/200"]),
]
LEVERAGE, LEVERAGE_COST = 2.0, 0.04  # Faktor, Kosten pro Jahr (Finanzierung, Spread)
WARMUP_DAYS = 300  # Kurse vor dem Teststart, damit auch lange Durchschnitte (200 Tage) bereitstehen


def leveraged(bars: list[Bar], factor: float = LEVERAGE, cost: float = LEVERAGE_COST) -> list[Bar]:
    """Künstliche Kursreihe eines täglich angepassten Hebelprodukts auf den Basiswert."""
    out, p = [], 100.0
    for prev, b in zip(bars, bars[1:]):
        p *= max(0.0, 1 + factor * (b.close / prev.close - 1) - cost / 252)
        out.append(Bar(b.time, p, p, p, p, b.volume))
    return out


def run_variants(cfg, bars: dict[str, list[Bar]], start: date, cut: date, end: date) -> list[dict]:
    """Jede Variante zweimal: Vergleichszeitraum (start..cut) und Prüfjahr (cut..end), je mit frischem Budget."""
    lev_bars = {s: (b if s == cfg.benchmark else leveraged(b)) for s, b in bars.items()}
    results = []
    for name, overrides, data in [(n, o, bars) for n, o in VARIANTS] + [(n, o, lev_bars) for n, o in LEVERAGED]:
        vcfg = _merge(copy.deepcopy(cfg), overrides)
        a = run_backtest(vcfg, data, start, cut)
        b = run_backtest(vcfg, data, cut, end)
        results.append({"name": name, "train": a, "test": b})
    return results


def format_variants(results: list[dict]) -> list[str]:
    a, b = results[0]["train"], results[0]["test"]
    lines = [
        f"VARIANTEN (nur Trend + Risikoregeln, ohne Nachrichten, Start {a['budget']:.0f} $, "
        f"Rendite auf das Eingezahlte)",
        f"  Zeitraum A {a['start']} bis {a['end']} | Prüfjahr B {b['start']} bis {b['end']}",
        f"  {a['benchmark'] + ' halten':28} A {a['benchmark_return_pct']:+7.1%}            | B {b['benchmark_return_pct']:+7.1%}",
    ]
    for r in sorted(results, key=lambda r: -r["train"]["return_pct"]):
        x, y = r["train"], r["test"]
        lines.append(f"  {r['name']:28} A {x['return_pct']:+7.1%} (Rückg. {x['max_drawdown_pct']:4.0%}, "
                     f"{x['trades']:3d} Tr.) | B {y['return_pct']:+7.1%} (Rückg. {y['max_drawdown_pct']:4.0%})"
                     + (" NOT-AUS" if x["halted"] or y["halted"] else ""))
    return lines
