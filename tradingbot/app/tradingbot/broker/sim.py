"""Offline-Simulator: zufällige Kurse, kein Internet nötig. Für Tests und Trockenübungen."""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from .base import Account, Bar, Broker, Fill, Position


class SimBroker(Broker):
    def __init__(self, cash: float, symbols: list[str], seed: int = 42, history_days: int = 120):
        self.cash = cash
        self.rng = random.Random(seed)
        self.holdings: dict[str, tuple[float, float]] = {}  # symbol -> (qty, avg_price)
        self.history: dict[str, list[Bar]] = {}
        start = datetime.now(timezone.utc) - timedelta(days=history_days)
        for s in symbols:
            price, drift = self.rng.uniform(50, 400), self.rng.uniform(-0.002, 0.003)
            bars = []
            for d in range(history_days):
                price *= math.exp(drift + self.rng.gauss(0, 0.018))
                bars.append(Bar(start + timedelta(days=d), price, price * 1.01, price * 0.99, price, 1e6))
            self.history[s] = bars

    def step(self, days: int = 1) -> None:
        """Simuliert weitere Handelstage."""
        for s, bars in self.history.items():
            for _ in range(days):
                last = bars[-1]
                price = last.close * math.exp(self.rng.gauss(0.0005, 0.018))
                bars.append(Bar(last.time + timedelta(days=1), price, price * 1.01, price * 0.99, price, 1e6))

    def set_price(self, symbol: str, price: float) -> None:
        last = self.history[symbol][-1]
        self.history[symbol].append(Bar(last.time + timedelta(days=1), price, price, price, price, 1e6))

    def account(self) -> Account:
        equity = self.cash + sum(p.market_value for p in self.positions().values())
        return Account(cash=self.cash, equity=equity, buying_power=self.cash)

    def positions(self) -> dict[str, Position]:
        return {s: Position(s, q, a, self.last_price(s)) for s, (q, a) in self.holdings.items()}

    def daily_bars(self, symbol: str, days: int) -> list[Bar]:
        return self.history[symbol][-days:]

    def last_price(self, symbol: str) -> float:
        return self.history[symbol][-1].close

    def market_open(self) -> bool:
        return True

    def buy_notional(self, symbol: str, amount: float) -> Fill | None:
        amount = min(amount, self.cash)
        if amount <= 0:
            return None
        price = self.last_price(symbol)
        qty = amount / price
        old_q, old_a = self.holdings.get(symbol, (0.0, 0.0))
        new_q = old_q + qty
        self.holdings[symbol] = (new_q, (old_q * old_a + qty * price) / new_q)
        self.cash -= amount
        return Fill(symbol, "buy", qty, price)

    def sell_qty(self, symbol: str, qty: float) -> Fill | None:
        if symbol not in self.holdings or qty <= 0:
            return None
        held, avg = self.holdings[symbol]
        qty = min(qty, held)
        if held - qty < 1e-9:
            return self.sell_all(symbol)
        self.holdings[symbol] = (held - qty, avg)
        price = self.last_price(symbol)
        self.cash += qty * price
        return Fill(symbol, "sell", qty, price)

    def sell_all(self, symbol: str) -> Fill | None:
        if symbol not in self.holdings:
            return None
        qty, _ = self.holdings.pop(symbol)
        price = self.last_price(symbol)
        self.cash += qty * price
        return Fill(symbol, "sell", qty, price)
