"""Broker-Schnittstelle: so kann Alpaca später z.B. durch Interactive Brokers ersetzt werden."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Account:
    cash: float
    equity: float
    buying_power: float


@dataclass
class Position:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float

    @property
    def market_value(self) -> float:
        return self.qty * self.current_price

    @property
    def pnl_pct(self) -> float:
        return self.current_price / self.avg_entry_price - 1 if self.avg_entry_price else 0.0


@dataclass
class Bar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Fill:
    symbol: str
    side: str
    qty: float
    price: float


class Broker(ABC):
    @abstractmethod
    def account(self) -> Account: ...

    @abstractmethod
    def positions(self) -> dict[str, Position]: ...

    @abstractmethod
    def daily_bars(self, symbol: str, days: int) -> list[Bar]: ...

    @abstractmethod
    def last_price(self, symbol: str) -> float: ...

    @abstractmethod
    def market_open(self) -> bool: ...

    @abstractmethod
    def buy_notional(self, symbol: str, amount: float) -> Fill | None: ...

    @abstractmethod
    def sell_all(self, symbol: str) -> Fill | None: ...

    def fetch_news(self, symbols: list[str], since: datetime) -> list[dict]:
        return []
