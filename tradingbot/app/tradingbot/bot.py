"""Hauptlogik: ein Handelszyklus und die Endlosschleife."""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime

from .broker.sim import SimBroker
from .earnings import EarningsCalendar
from .homeassistant import Reporter
from .news import MARKET, NewsAnalyzer
from .risk import RiskManager
from .storage import Storage
from .strategy import combine, trend_score

log = logging.getLogger(__name__)


BENCHMARK_NAMES = {"URTH": "MSCI World", "SPY": "S&P 500"}

class TradingBot:
    def __init__(self, cfg, broker, storage: Storage | None = None, reporter: Reporter | None = None):
        self.cfg = cfg
        self.reporter = reporter or Reporter()
        self.status = "gestartet"
        self.broker = broker
        self.storage = storage or Storage(cfg.db_path)
        self.risk = RiskManager(cfg, self.storage)
        self.news = NewsAnalyzer(cfg, self.storage, broker)
        # Termine nur im echten Betrieb (im Backtest wären es heutige Termine, nicht die damaligen)
        self.earnings = None if isinstance(broker, SimBroker) else EarningsCalendar(self.storage)
        self.signals = {}

    def _own_positions(self):
        """Nur Positionen, die der Bot selbst eröffnet hat (manuelle Käufe bleiben unberührt)."""
        held = self.broker.positions()
        meta = self.storage.all_meta()
        for sym in list(meta):
            if sym not in held:
                opened = self.storage.get_meta(sym)[2]
                fill = self.broker.last_sell_fill(sym, datetime.fromisoformat(opened))
                if fill:
                    self._record_sell(sym, fill, "Verkauf beim Broker (Stop-Order)", meta, date.today())
                else:
                    log.warning("%s nicht mehr im Depot (extern verkauft?), entferne aus Verwaltung", sym)
                    self.storage.close_meta(sym)
                    meta.pop(sym)
        return {s: held[s] for s in meta}, meta

    def _broker_stop(self, pos, high: float) -> None:
        """Stop-Order beim Broker auf dem Niveau, ab dem der Bot selbst verkaufen würde."""
        if not self.cfg.risk.broker_stops:
            return
        r = self.cfg.risk
        stop = pos.avg_entry_price * (1 - r.stop_loss_pct)
        trail = high * (1 - r.trailing_stop_pct)
        if trail > pos.avg_entry_price:
            stop = max(stop, trail)
        try:
            self.broker.ensure_stop(pos.symbol, pos.qty, stop)
        except Exception:
            log.exception("Stop-Order für %s nicht möglich", pos.symbol)

    def _top_up(self, signals: dict, meta: dict, soon: dict | None, today: date) -> None:
        """Nachkaufen, wenn eine gehaltene Aktie nach Einzahlungen deutlich unter ihrer Zielgröße liegt."""
        r, st = self.cfg.risk, self.cfg.strategy
        target = self.risk.bot_capital() * r.max_position_pct
        for sym in sorted(meta, key=lambda s: meta[s]):
            sig = signals.get(sym)
            gap = target - meta[sym]
            if not sig or sig.score < st.buy_threshold or gap < max(r.min_order_value, target * r.top_up_min_gap_pct):
                continue
            if self.news.latest_shock(sym) <= st.panic_news_threshold:
                continue
            if soon is None and self.earnings:
                soon = self.earnings.upcoming(self.cfg.watchlist, today, self.cfg.news.earnings_guard_days)
            if soon and sym in soon:
                continue
            amount = min(gap, self.risk.free_budget(sum(meta.values()), self.broker.account().cash))
            if amount < r.min_order_value:
                return
            fill = self.broker.buy_notional(sym, amount)
            if not fill:
                continue
            cost = fill.qty * fill.price
            self.storage.open_meta(sym, cost, fill.price)
            meta[sym] = self.storage.all_meta()[sym]
            reason = f"Nachkauf auf Zielgröße, Signal {sig.score:+.2f}"
            self.storage.record_trade(sym, "buy", fill.qty, fill.price, reason)
            held = self.broker.positions().get(sym)
            if held:
                self._broker_stop(held, self.storage.update_high(sym, fill.price))
            log.info("NACHKAUF %s %.4f @ %.2f (%.2f) | %s", sym, fill.qty, fill.price, cost, reason)
            self.reporter.notify(f"Tradingbot: {sym} nachgekauft", f"{cost:.2f} $ zu {fill.price:.2f} $")

    def _sell(self, symbol: str, reason: str, meta: dict, today: date) -> None:
        fill = self.broker.sell_all(symbol)
        if fill:
            self._record_sell(symbol, fill, reason, meta, today)

    def _record_sell(self, symbol: str, fill, reason: str, meta: dict, today: date) -> None:
        pnl = fill.qty * fill.price - meta.get(symbol, 0.0)
        self.storage.record_trade(symbol, "sell", fill.qty, fill.price, reason, pnl)
        self.storage.close_meta(symbol)
        self.storage.set(f"sold:{symbol}", today.isoformat())
        meta.pop(symbol, None)
        log.info("VERKAUF %s %.4f @ %.2f | %s | G/V %+.2f", symbol, fill.qty, fill.price, reason, pnl)
        self.reporter.notify(f"Tradingbot: {symbol} verkauft", f"{reason}, Gewinn/Verlust {pnl:+.2f} $")

    def in_cooldown(self, symbol: str, today: date) -> bool:
        sold = self.storage.get(f"sold:{symbol}")
        return bool(sold) and (today - date.fromisoformat(sold)).days < self.cfg.risk.rebuy_cooldown_days

    def run_cycle(self, today: date | None = None) -> None:
        try:
            self._cycle(today or date.today())
        finally:
            self._publish()

    def _publish(self) -> None:
        try:
            positions, meta = self._own_positions()
            capital = self.risk.bot_capital()
            last = self.storage.recent_trades(1)
            bench = self._benchmark_value()
            invested = sum(meta.values())
            value = capital - invested + sum(p.market_value for p in positions.values())
            self.reporter.publish({
                "benchmark_value": bench,
                "benchmark": BENCHMARK_NAMES.get(self.cfg.benchmark, self.cfg.benchmark),
                "value": value,
                "capital": capital,
                "realized_pnl": self.storage.realized_pnl(),
                "positions": sorted(meta),
                "status": self.status,
                "mode": self.cfg.mode,
                "halted": self.risk.halted,
                "last_trade": f"{last[0][2]} {last[0][1]} ({last[0][0][:16]})" if last else None,
                **self._details(positions, meta, value, capital, invested),
            })
        except Exception:
            log.exception("Status konnte nicht gemeldet werden")

    def _details(self, positions, meta, value, capital, invested) -> dict:
        """Zusätzliche Angaben für das Dashboard (Positionen, Trades, Nachrichten, Risiko)."""
        r = self.cfg.risk
        details = []
        for sym in sorted(meta):
            p, cost = positions.get(sym), meta[sym]
            mv = p.market_value if p else cost
            details.append({
                "symbol": sym,
                "stueck": round(p.qty, 4) if p else None,
                "einstand": round(p.avg_entry_price, 2) if p else None,
                "kurs": round(p.current_price, 2) if p else None,
                "wert": round(mv, 2),
                "gewinn": round(mv - cost, 2),
                "prozent": round((mv / cost - 1) * 100, 2) if cost else 0.0,
            })
        trades = [
            {"zeit": t, "symbol": sym, "art": "Kauf" if side == "buy" else "Verkauf", "stueck": round(qty, 4),
             "preis": round(price, 2), "gewinn": round(pnl or 0.0, 2), "grund": reason}
            for t, sym, side, qty, price, pnl, reason in self.storage.recent_trades(10)
        ]
        news = [
            {"zeit": t, "symbol": "Markt" if sym == MARKET else sym, "bewertung": round(score, 2), "titel": h[:140]}
            for t, sym, score, h in self.storage.recent_news(8)
        ]
        peak = max(float(self.storage.get("peak_value", value)), value)
        day_start = float(self.storage.get("day_start_value", value))
        return {
            "positions_detail": details,
            "invested": invested,
            "cash": capital - invested,
            "unrealized_pnl": value - capital,
            "paid_in": r.start_budget + self.risk.deposits(),
            "trades": trades,
            "trade_count": self.storage.trade_count(),
            "market_sentiment": self.news.score(MARKET),
            "news_scores": {s: round(self.news.score(s), 2) for s in self.cfg.watchlist},
            "news": news,
            "signals": {s: {"trend": round(x.trend, 2), "news": round(x.news, 2), "gesamt": round(x.score, 2)}
                        for s, x in self.signals.items()},
            "peak_value": peak,
            "drawdown_pct": (1 - value / peak) * 100 if peak else 0.0,
            "day_change_pct": (value / day_start - 1) * 100 if day_start else 0.0,
            "max_drawdown_pct": r.max_drawdown_pct * 100,
            "daily_loss_limit_pct": r.daily_loss_limit_pct * 100,
            "stop_loss_pct": r.stop_loss_pct * 100,
            "trailing_stop_pct": r.trailing_stop_pct * 100,
            "take_profit_pct": r.take_profit_pct * 100,
            "max_positions": r.max_positions,
            "strategy": os.getenv("TRADINGBOT_PROFILE") or "standard",
            "watchlist": list(self.cfg.watchlist),
            "interval_minutes": self.cfg.interval_minutes,
            "last_run": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    def _benchmark_value(self) -> float | None:
        """Was Startbudget und Einzahlungen wert wären, hätte man sie jeweils in den Vergleichs-ETF gesteckt."""
        sym = self.cfg.benchmark
        if not sym:
            return None
        try:
            price = self.broker.last_price(sym)
        except Exception:
            log.warning("Kurs für Vergleich %s nicht verfügbar", sym)
            return None
        start = self.storage.get(f"benchmark_start_{sym}")
        if not start:
            self.storage.set(f"benchmark_start_{sym}", price)
            start = price
        units = float(self.storage.get(f"benchmark_units_{sym}", 0))
        new = self.risk.deposits() - float(self.storage.get(f"benchmark_deposits_{sym}", 0))
        if new > 0:
            units += new / price
            self.storage.set(f"benchmark_units_{sym}", units)
            self.storage.set(f"benchmark_deposits_{sym}", self.risk.deposits())
        return self.cfg.risk.start_budget * price / float(start) + units * price

    def _news_panic(self, sym: str) -> bool:
        """Panik-Verkauf? Bei Trend-Strategien reicht eine einzelne schlechte Schlagzeile nicht."""
        st = self.cfg.strategy
        shock = self.news.latest_shock(sym)
        if shock > st.panic_news_threshold:
            return False
        if not st.panic_needs_confirmation or shock <= st.panic_severe_threshold:
            return True
        return self.news.score(sym) <= st.panic_confirm_score

    def _cycle(self, today: date) -> None:
        if self.risk.halted:
            self.status = "Not-Aus"
            log.error("Bot ist per Not-Aus angehalten (max. Drawdown). 'python -m tradingbot reset-halt' zum Fortsetzen.")
            return
        if deposit := self.risk.apply_deposits(today):
            log.info("Monatliche Einzahlung gebucht: +%.2f $, Kapital jetzt %.2f $", deposit, self.risk.bot_capital())
        if extra := self.risk.apply_extra_deposits():
            log.info("Sonderzahlung gebucht: +%.2f $, Kapital jetzt %.2f $", extra, self.risk.bot_capital())
        try:
            self.news.refresh()
        except Exception:
            log.exception("Nachrichtenabruf fehlgeschlagen")
        if not self.broker.market_open():
            self.status = "Börse geschlossen"
            log.info("Börse geschlossen, nur Nachrichten aktualisiert.")
            return

        positions, meta = self._own_positions()
        capital = self.risk.bot_capital()
        bot_value = capital - sum(meta.values()) + sum(p.market_value for p in positions.values())
        limit = self.risk.check_limits(bot_value, today)
        if limit == "stop":
            self.status = "Not-Aus"
            log.error("Max. Drawdown erreicht: verkaufe alles und halte an.")
            self.reporter.notify("Tradingbot: NOT-AUS", "Maximaler Verlust erreicht, alle Positionen werden verkauft.")
            for sym in list(positions):
                self._sell(sym, "Not-Aus Drawdown", meta, today)
            return

        market = self.news.score(MARKET)
        st = self.cfg.strategy
        signals = {}
        for sym in self.cfg.watchlist:
            try:
                bars = self.broker.daily_bars(sym, st.sma_slow + 5)
            except Exception:
                log.exception("Kursdaten für %s fehlen", sym)
                continue
            signals[sym] = combine(sym, trend_score(bars, st.sma_fast, st.sma_slow), self.news.score(sym), market, self.cfg)
        self.signals = signals

        # 1) Verkäufe
        for sym, pos in positions.items():
            high = self.storage.update_high(sym, pos.current_price)
            reason = self.risk.exit_reason(pos.pnl_pct, pos.current_price, high)
            if not reason and self._news_panic(sym):
                reason = "sehr negative Nachricht"
            sig = signals.get(sym)
            if not reason and sig and sig.score <= st.sell_threshold:
                reason = f"Signal negativ ({sig.score:+.2f})"
            if reason:
                self._sell(sym, reason, meta, today)
            else:
                self._broker_stop(pos, high)

        # 2) Käufe
        self.status = "Tageslimit erreicht" if limit == "day" else "handelt"
        if limit == "day":
            log.warning("Tagesverlust-Limit erreicht: heute keine neuen Käufe.")
        else:
            candidates = sorted(
                (
                    s for s in signals.values()
                    if s.score >= st.buy_threshold and s.symbol not in meta and not self.in_cooldown(s.symbol, today)
                ),
                key=lambda s: s.score, reverse=True,
            )
            soon = self.earnings.upcoming(self.cfg.watchlist, today, self.cfg.news.earnings_guard_days) \
                if self.earnings and candidates else {}
            for sig in candidates:
                if len(meta) >= self.cfg.risk.max_positions:
                    break
                if self.news.latest_shock(sig.symbol) <= st.panic_news_threshold:
                    continue
                if sig.symbol in soon:  # Kurs springt bei Quartalszahlen oft stark, erst danach einsteigen
                    log.info("Kein Kauf %s: Quartalszahlen am %s", sig.symbol, f"{soon[sig.symbol]:%d.%m.}")
                    continue
                amount = self.risk.position_size(sum(meta.values()), self.broker.account().cash)
                if not amount:
                    break
                fill = self.broker.buy_notional(sig.symbol, amount)
                if not fill:
                    continue
                cost = fill.qty * fill.price
                self.storage.open_meta(sig.symbol, cost, fill.price)
                meta[sig.symbol] = self.storage.all_meta()[sig.symbol]
                reason = f"Trend {sig.trend:+.2f}, News {sig.news:+.2f}, Markt {sig.market:+.2f}"
                self.storage.record_trade(sig.symbol, "buy", fill.qty, fill.price, reason)
                held = self.broker.positions().get(sig.symbol)
                if held:
                    self._broker_stop(held, fill.price)
                log.info("KAUF %s %.4f @ %.2f (%.2f) | %s", sig.symbol, fill.qty, fill.price, cost, reason)
                self.reporter.notify(f"Tradingbot: {sig.symbol} gekauft", f"{cost:.2f} $ zu {fill.price:.2f} $ ({reason})")
            self._top_up(signals, meta, soon if candidates else None, today)

        positions, meta = self._own_positions()
        value = self.risk.bot_capital() - sum(meta.values()) + sum(p.market_value for p in positions.values())
        self.storage.record_equity(value, self.risk.bot_capital(), self.broker.account().equity)
        log.info("Bot-Wert %.2f | Kapital %.2f | Positionen: %s", value, self.risk.bot_capital(), ", ".join(meta) or "keine")

    def run_forever(self) -> None:
        log.info("Tradingbot gestartet im Modus '%s', Intervall %d min", self.cfg.mode, self.cfg.interval_minutes)
        while True:
            try:
                self.run_cycle()
            except Exception:
                log.exception("Fehler im Handelszyklus, versuche es im nächsten Intervall erneut")
            time.sleep(self.cfg.interval_minutes * 60)
