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


def run_backtest(cfg, bars: dict[str, list[Bar]]) -> dict:
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
    days = calendar[cfg.strategy.sma_slow + 5:]
    if not days:
        raise ValueError("zu wenig Kursdaten für einen Backtest")

    bot_logger = logging.getLogger("tradingbot.bot")
    level = bot_logger.level
    bot_logger.setLevel(logging.WARNING)
    peak, max_dd, bench_start = budget, 0.0, None
    try:
        for d in days:
            broker.set_date(d)
            bot.run_cycle(today=d)
            value = broker.account().equity
            peak = max(peak, value)
            max_dd = max(max_dd, 1 - value / peak)
            if bench and bench_start is None:
                bench_start = broker.last_price(bench)
    finally:
        bot_logger.setLevel(level)

    trades = bot.storage.recent_trades(100_000)
    sells = [t for t in trades if t[2] == "sell"]
    final = broker.account().equity
    return {
        "start": days[0], "end": days[-1], "budget": budget, "final": final,
        "return_pct": final / budget - 1, "max_drawdown_pct": max_dd,
        "trades": len(trades), "sells": len(sells),
        "win_rate": sum(1 for t in sells if t[5] > 0) / len(sells) if sells else 0.0,
        "halted": bot.risk.halted,
        "benchmark": bench,
        "benchmark_return_pct": broker.last_price(bench) / bench_start - 1 if bench else None,
    }


def format_result(r: dict) -> list[str]:
    lines = [
        f"BACKTEST {r['start']} bis {r['end']} (nur Trend + Risikoregeln, ohne Nachrichten)",
        f"  Bot: {r['budget']:.0f} $ -> {r['final']:.2f} $ ({r['return_pct']:+.1%}), "
        f"größter Rückgang {r['max_drawdown_pct']:.1%}",
        f"  {r['trades']} Trades, {r['sells']} Verkäufe, davon {r['win_rate']:.0%} mit Gewinn",
    ]
    if r["halted"]:
        lines.append("  Achtung: Not-Aus (max. Verlust) wurde im Testzeitraum ausgelöst, danach kein Handel mehr")
    if r["benchmark"]:
        diff = r["return_pct"] - r["benchmark_return_pct"]
        lines.append(f"  Vergleich {r['benchmark']} halten: {r['benchmark_return_pct']:+.1%} "
                     f"-> Bot {'besser' if diff >= 0 else 'schlechter'} um {abs(diff):.1%}-Punkte")
    return lines
