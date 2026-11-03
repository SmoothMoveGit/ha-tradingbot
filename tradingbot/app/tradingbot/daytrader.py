"""Zweiter Bot zum Vergleich: Daytrading mit 5-Minuten-Kursen.

Kauft Ausbrüche über das Hoch der letzten halben Stunde (Kurs über dem Tagesdurchschnitt VWAP),
verkauft bei kleinem Gewinn oder Verlust und ist zum Handelsschluss immer komplett draußen.
Eigenes Alpaca-Konto, eigene Datenbank, eigene Sensoren (sensor.daytrader_*).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .broker.base import Bar, Fill, Position
from .homeassistant import Reporter
from .storage import Storage

log = logging.getLogger("tradingbot.daytrader")
NY = ZoneInfo("America/New_York")


@dataclass
class DayConfig:
    watchlist: list
    start_budget: float = 1100.0
    max_positions: int = 5
    position_pct: float = 0.20
    take_profit_pct: float = 0.015
    stop_loss_pct: float = 0.010
    breakout_bars: int = 6          # Hoch der letzten 6 Kerzen (30 min) muss überschritten werden
    min_momentum: float = 0.003     # mindestens +0,3 % in diesen 30 min
    no_entry_first_min: int = 15    # erste Viertelstunde ist zu wild
    no_entry_last_min: int = 45
    flat_before_close_min: int = 15
    daily_loss_limit_pct: float = 0.03
    interval_minutes: int = 2
    min_order_value: float = 10.0


def vwap(bars: list[Bar]) -> float:
    vol = sum(b.volume for b in bars)
    if not vol:
        return sum(b.close for b in bars) / len(bars)
    return sum((b.high + b.low + b.close) / 3 * b.volume for b in bars) / vol


def entry_signal(bars: list[Bar], cfg: DayConfig) -> float | None:
    """Stärke des Ausbruchs (Kursanstieg der letzten 30 min) oder None, wenn kein Kauf."""
    n = cfg.breakout_bars
    if len(bars) < n + 1:
        return None
    last = bars[-1].close
    prior_high = max(b.high for b in bars[-n - 1:-1])
    momentum = last / bars[-n - 1].close - 1
    if last > prior_high and last > vwap(bars) and momentum >= cfg.min_momentum:
        return momentum
    return None


class DayTrader:
    def __init__(self, cfg: DayConfig, broker, storage: Storage, reporter: Reporter | None = None):
        self.cfg = cfg
        self.broker = broker
        self.storage = storage
        self.reporter = reporter or Reporter()
        self.status = "gestartet"
        self.traded_today: dict[str, date] = {}

    def capital(self) -> float:
        return self.cfg.start_budget + self.storage.realized_pnl()

    def _realized_today(self, today: date) -> float:
        rows = self.storage.db.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE time>=?",
                                       (datetime.combine(today, datetime.min.time(), NY).astimezone(timezone.utc).isoformat(),)
                                       ).fetchone()
        return rows[0]

    def _sell(self, sym: str, reason: str, meta: dict, now: datetime) -> None:
        fill = self.broker.sell_all(sym)
        if not fill:
            return
        pnl = fill.qty * fill.price - meta.get(sym, 0.0)
        self.storage.record_trade(sym, "sell", fill.qty, fill.price, reason, pnl, when=now)
        self.storage.close_meta(sym)
        meta.pop(sym, None)
        log.info("VERKAUF %s %.4f @ %.2f | %s | G/V %+.2f", sym, fill.qty, fill.price, reason, pnl)

    def cycle(self, now: datetime | None = None) -> None:
        now = (now or datetime.now(timezone.utc)).astimezone(NY)
        today = now.date()
        c = self.cfg
        if not self.broker.market_open():
            self.status = "Börse geschlossen"
            return
        held = self.broker.positions()
        meta = {s: v for s, v in self.storage.all_meta().items()}
        for sym in list(meta):  # beim Broker per Stop verkauft
            if sym not in held:
                fill = self.broker.last_sell_fill(sym, datetime.fromisoformat(self.storage.get_meta(sym)[2]))
                if fill:
                    pnl = fill.qty * fill.price - meta[sym]
                    self.storage.record_trade(sym, "sell", fill.qty, fill.price, "Stop beim Broker", pnl, when=now)
                self.storage.close_meta(sym)
                meta.pop(sym)
        mins_left = self.broker.minutes_to_close(now)
        if mins_left <= c.flat_before_close_min:
            for sym in list(meta):
                self._sell(sym, "Handelsschluss", meta, now)
            self.status = "Tagesende, alles verkauft"
            return

        bars = self.broker.intraday_bars(c.watchlist, now)
        for sym in list(meta):
            pos = held.get(sym)
            if not pos:
                continue
            if pos.pnl_pct >= c.take_profit_pct:
                self._sell(sym, f"Gewinnmitnahme {pos.pnl_pct:+.1%}", meta, now)
            elif pos.pnl_pct <= -c.stop_loss_pct:
                self._sell(sym, f"Stop-Loss {pos.pnl_pct:+.1%}", meta, now)

        unrealized = sum(held[s].market_value - meta[s] for s in meta if s in held)
        if self._realized_today(today) + unrealized <= -c.daily_loss_limit_pct * self.capital():
            self.status = "Tageslimit erreicht"
            return
        open_min = (now - now.replace(hour=9, minute=30, second=0, microsecond=0)).total_seconds() / 60
        if open_min < c.no_entry_first_min or mins_left <= c.no_entry_last_min:
            self.status = "handelt (keine neuen Käufe)"
            return
        self.status = "handelt"
        candidates = []
        for sym in c.watchlist:
            if sym in meta or self.traded_today.get(sym) == today:
                continue
            strength = entry_signal(bars.get(sym, []), c)
            if strength is not None:
                candidates.append((strength, sym))
        cash = self.broker.account().cash
        for strength, sym in sorted(candidates, reverse=True):
            if len(meta) >= c.max_positions:
                break
            free = min(self.capital() - sum(meta.values()), cash)
            amount = min(self.capital() * c.position_pct, free)
            if amount < c.min_order_value:
                break
            fill = self.broker.buy_notional(sym, amount)
            if not fill:
                continue
            cost = fill.qty * fill.price
            cash -= cost
            self.storage.open_meta(sym, cost, fill.price, when=now)
            meta[sym] = cost
            self.traded_today[sym] = today
            self.storage.record_trade(sym, "buy", fill.qty, fill.price, f"Ausbruch {strength:+.1%} in 30 min", when=now)
            self.broker.ensure_stop(sym, fill.qty, fill.price * (1 - c.stop_loss_pct))
            log.info("KAUF %s %.4f @ %.2f (%.2f) | Ausbruch %+.1f%%", sym, fill.qty, fill.price, cost, strength * 100)

    def publish(self) -> None:
        try:
            held = self.broker.positions()
            meta = self.storage.all_meta()
            value = self.capital() - sum(meta.values()) + sum(held[s].market_value for s in meta if s in held)
            trades = [
                {"zeit": t, "symbol": sym, "art": "Kauf" if side == "buy" else "Verkauf", "preis": round(price, 2),
                 "gewinn": round(pnl or 0.0, 2), "grund": reason}
                for t, sym, side, qty, price, pnl, reason in self.storage.recent_trades(10)
            ]
            self.reporter.publish_daytrader({
                "value": value, "capital": self.capital(), "start_budget": self.cfg.start_budget,
                "realized_pnl": self.storage.realized_pnl(), "positions": sorted(meta),
                "status": self.status, "trade_count": self.storage.trade_count(), "trades": trades,
            })
        except Exception:
            log.exception("Daytrader-Status konnte nicht gemeldet werden")

    def run_forever(self) -> None:
        log.info("Daytrader gestartet, Startbudget %.2f $, Intervall %d min", self.cfg.start_budget, self.cfg.interval_minutes)
        while True:
            try:
                self.cycle()
            except Exception:
                log.exception("Fehler im Daytrader-Zyklus")
            self.publish()
            time.sleep(self.cfg.interval_minutes * 60)


class IntradaySim:
    """Spielt historische 5-Minuten-Kerzen ab (für den Backtest). Ausführung zum Schlusskurs der Kerze."""

    def __init__(self, bars: dict[str, list[Bar]], cash: float, slippage: float = 0.0005):
        self.bars = bars
        self.cash = cash
        self.slippage = slippage  # halbe Spanne zwischen Kauf- und Verkaufskurs
        self.holdings: dict[str, tuple[float, float]] = {}
        self.now = None
        self.idx = {s: 0 for s in bars}

    def set_time(self, now: datetime) -> None:
        self.now = now
        for s, bs in self.bars.items():
            i = self.idx[s]
            while i < len(bs) and bs[i].time + timedelta(minutes=5) <= now:
                i += 1
            self.idx[s] = i

    def _price(self, sym: str) -> float:
        i = self.idx[sym]
        return self.bars[sym][i - 1].close

    def market_open(self) -> bool:
        return True

    def minutes_to_close(self, now: datetime) -> float:
        n = now.astimezone(NY)
        return (n.replace(hour=16, minute=0, second=0, microsecond=0) - n).total_seconds() / 60

    def intraday_bars(self, symbols, now) -> dict[str, list[Bar]]:
        day = now.astimezone(NY).date()
        out = {}
        for s in symbols:
            bs = self.bars.get(s, [])[: self.idx.get(s, 0)]
            out[s] = [b for b in bs if b.time.astimezone(NY).date() == day]
        return out

    def positions(self) -> dict[str, Position]:
        return {s: Position(s, q, p, self._price(s)) for s, (q, p) in self.holdings.items()}

    def account(self):
        from .broker.base import Account
        eq = self.cash + sum(p.market_value for p in self.positions().values())
        return Account(self.cash, eq, self.cash)

    def buy_notional(self, sym: str, amount: float) -> Fill | None:
        if not self.idx.get(sym):
            return None
        price = self._price(sym) * (1 + self.slippage)
        qty = amount / price
        self.cash -= amount
        self.holdings[sym] = (qty, price)
        return Fill(sym, "buy", qty, price)

    def sell_all(self, sym: str) -> Fill | None:
        if sym not in self.holdings:
            return None
        qty, _ = self.holdings.pop(sym)
        price = self._price(sym) * (1 - self.slippage)
        self.cash += qty * price
        return Fill(sym, "sell", qty, price)

    def ensure_stop(self, *a) -> None:
        pass

    def last_sell_fill(self, *a):
        return None


def backtest(cfg: DayConfig, bars: dict[str, list[Bar]]) -> dict:
    """Daytrading-Regeln über historische 5-Minuten-Kerzen, alle 5 min ein Zyklus."""
    sim = IntradaySim(bars, cfg.start_budget)
    bot = DayTrader(cfg, sim, Storage(":memory:"))
    times = sorted({b.time + timedelta(minutes=5) for bs in bars.values() for b in bs
                    if (9, 30) <= (b.time.astimezone(NY).hour, b.time.astimezone(NY).minute) < (16, 0)})
    days = set()
    level = log.level
    log.setLevel(logging.WARNING)  # Backtest-Trades nicht ins Protokoll, sonst sehen sie echt aus
    try:
        for t in times:
            days.add(t.astimezone(NY).date())
            sim.set_time(t)
            bot.cycle(t)
    finally:
        log.setLevel(level)
    trades = bot.storage.db.execute("SELECT pnl FROM trades WHERE side='sell'").fetchall()
    wins = sum(1 for (p,) in trades if p > 0)
    return {"start": cfg.start_budget, "end": bot.capital(), "days": len(days), "trades": len(trades),
            "win_rate": wins / len(trades) if trades else 0.0}


def config_from_env(watchlist: list) -> DayConfig:
    return DayConfig(watchlist=watchlist, start_budget=float(os.getenv("DAYTRADER_BUDGET") or 1100))
