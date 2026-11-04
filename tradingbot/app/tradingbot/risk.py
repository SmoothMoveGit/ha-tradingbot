"""Risikoregeln: Budget, Positionsgrößen, Stops und Not-Aus."""
from __future__ import annotations

from datetime import date


class RiskManager:
    def __init__(self, cfg, storage):
        self.r = cfg.risk
        self.storage = storage

    def deposits(self) -> float:
        return float(self.storage.get("deposits_total", 0))

    def apply_deposits(self, today: date) -> float:
        """Bucht die monatliche Einzahlung, einmal pro neuem Kalendermonat. Gibt den neuen Betrag zurück."""
        month = today.year * 12 + today.month - 1
        last = self.storage.get("deposit_month")
        self.storage.set("deposit_month", month)
        if last is None or not self.r.monthly_deposit or month <= int(last):
            return 0.0
        amount = self.r.monthly_deposit * (month - int(last))
        self.storage.set("deposits_total", self.deposits() + amount)
        return amount

    def apply_extra_deposits(self) -> float:
        """Bucht den neuen Teil der Sonderzahlungen (Option ist die Summe aller Sonderzahlungen)."""
        booked = float(self.storage.get("extra_deposits_booked", 0))
        amount = self.r.extra_deposits - booked
        if amount <= 0:
            return 0.0
        self.storage.set("extra_deposits_booked", self.r.extra_deposits)
        self.storage.set("deposits_total", self.deposits() + amount)
        return amount

    def bot_capital(self) -> float:
        """Startguthaben plus Einzahlungen plus realisierte Gewinne (falls erlaubt) bzw. minus Verluste."""
        pnl = self.storage.realized_pnl()
        if not self.r.reinvest_profits:
            pnl = min(pnl, 0.0)
        return self.r.start_budget + self.deposits() + pnl

    def free_budget(self, invested_cost: float, broker_cash: float) -> float:
        usable = self.bot_capital() * (1 - self.r.min_cash_reserve_pct) - invested_cost
        return max(0.0, min(usable, broker_cash))

    def position_size(self, invested_cost: float, broker_cash: float) -> float:
        amount = min(self.bot_capital() * self.r.max_position_pct, self.free_budget(invested_cost, broker_cash))
        return amount if amount >= self.r.min_order_value else 0.0

    def exit_reason(self, pnl_pct: float, price: float, high: float) -> str | None:
        if pnl_pct <= -self.r.stop_loss_pct:
            return f"Stop-Loss ({pnl_pct:+.1%})"
        if pnl_pct >= self.r.take_profit_pct:
            return f"Gewinnmitnahme ({pnl_pct:+.1%})"
        if high > 0 and price <= high * (1 - self.r.trailing_stop_pct) and pnl_pct > 0:
            return f"Trailing-Stop ({price / high - 1:+.1%} vom Hoch)"
        return None

    # Not-Aus
    def check_limits(self, bot_value: float, today: date | None = None) -> str | None:
        """Gibt 'day' (heute keine Käufe), 'stop' (alles verkaufen, Bot anhalten) oder None zurück."""
        today = (today or date.today()).isoformat()
        if self.storage.get("day") != today:
            # Bezug ist der Schlusswert des letzten Handelstags (wie bei Börsenkursen), Einzahlungen
            # seitdem zählen nicht als Gewinn. Ohne Vortag: aktueller Wert.
            last, last_cap = self.storage.get("last_value"), self.storage.get("last_capital")
            if last is None:  # ältere Versionen: letzter Eintrag im Verlauf
                row = self.storage.db.execute(
                    "SELECT bot_value, bot_capital FROM equity ORDER BY time DESC LIMIT 1").fetchone()
                if row:
                    last, last_cap = row
            start = bot_value if last is None else \
                float(last) + self.bot_capital() - float(last_cap if last_cap is not None else self.bot_capital())
            self.storage.set("day", today)
            self.storage.set("day_start_value", start)
        day_start = float(self.storage.get("day_start_value", bot_value))
        peak = max(float(self.storage.get("peak_value", bot_value)), bot_value)
        self.storage.set("peak_value", peak)
        if bot_value < peak * (1 - self.r.max_drawdown_pct):
            self.storage.set("halted", "1")
            return "stop"
        if bot_value < day_start * (1 - self.r.daily_loss_limit_pct):
            return "day"
        return None

    def remember_close(self, bot_value: float) -> None:
        """Nach jedem Handelszyklus: letzter Wert als Bezug für den nächsten Tag."""
        self.storage.set("last_value", bot_value)
        self.storage.set("last_capital", self.bot_capital())

    @property
    def halted(self) -> bool:
        return self.storage.get("halted") == "1"

    def reset_halt(self) -> None:
        self.storage.set("halted", "0")
        self.storage.set("peak_value", self.bot_capital())
