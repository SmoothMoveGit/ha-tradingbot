"""Alpaca-Anbindung (Paper oder Live). Unterstützt Bruchteilsaktien über Betragsorders."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from alpaca.common.exceptions import APIError
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest, StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from .base import Account, Bar, Broker, Fill, Position

log = logging.getLogger(__name__)


class AlpacaBroker(Broker):
    def __init__(self, key: str | None, secret: str | None, paper: bool = True):
        if not key or not secret:
            raise SystemExit("ALPACA_API_KEY und ALPACA_SECRET_KEY fehlen (siehe .env.example).")
        self.paper = paper
        self.trading = TradingClient(key, secret, paper=paper)
        self.data = StockHistoricalDataClient(key, secret)
        self.news = NewsClient(key, secret)

    def account(self) -> Account:
        a = self.trading.get_account()
        return Account(cash=float(a.cash), equity=float(a.equity), buying_power=float(a.buying_power))

    def positions(self) -> dict[str, Position]:
        return {
            p.symbol: Position(p.symbol, float(p.qty), float(p.avg_entry_price), float(p.current_price))
            for p in self.trading.get_all_positions()
        }

    def daily_bars(self, symbol: str, days: int) -> list[Bar]:
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=datetime.now(timezone.utc) - timedelta(days=int(days * 1.6) + 5),
            feed=DataFeed.IEX,  # kostenloser Datenfeed
        )
        bars = self.data.get_stock_bars(req).data.get(symbol, [])
        return [Bar(b.timestamp, b.open, b.high, b.low, b.close, b.volume) for b in bars][-days:]

    def last_price(self, symbol: str) -> float:
        req = StockLatestTradeRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
        return float(self.data.get_stock_latest_trade(req)[symbol].price)

    def market_open(self) -> bool:
        return bool(self.trading.get_clock().is_open)

    def _wait_fill(self, order_id, timeout: float = 30.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            o = self.trading.get_order_by_id(order_id)
            if o.status in ("filled", "canceled", "rejected", "expired"):
                return o
            time.sleep(1)
        return self.trading.get_order_by_id(order_id)

    def buy_notional(self, symbol: str, amount: float) -> Fill | None:
        req = MarketOrderRequest(
            symbol=symbol, notional=round(amount, 2), side=OrderSide.BUY, time_in_force=TimeInForce.DAY
        )
        try:
            o = self._wait_fill(self.trading.submit_order(req).id)
        except APIError as e:
            log.error("Kauf %s abgelehnt: %s", symbol, e)
            return None
        if not o.filled_qty or float(o.filled_qty) == 0:
            log.warning("Kauf %s nicht ausgeführt (Status %s)", symbol, o.status)
            return None
        return Fill(symbol, "buy", float(o.filled_qty), float(o.filled_avg_price))

    def sell_all(self, symbol: str) -> Fill | None:
        try:
            o = self._wait_fill(self.trading.close_position(symbol).id)
        except APIError as e:
            log.error("Verkauf %s fehlgeschlagen: %s", symbol, e)
            return None
        if not o.filled_qty or float(o.filled_qty) == 0:
            return None
        return Fill(symbol, "sell", float(o.filled_qty), float(o.filled_avg_price))

    def fetch_news(self, symbols: list[str], since: datetime) -> list[dict]:
        try:
            res = self.news.get_news(NewsRequest(symbols=",".join(symbols), start=since, limit=50))
        except APIError as e:
            log.warning("Alpaca-News nicht abrufbar: %s", e)
            return []
        return [
            {
                "id": f"alpaca-{n.id}",
                "time": n.created_at,
                "headline": n.headline,
                "summary": n.summary or "",
                "source": n.source,
                "url": n.url,
                "symbols": list(n.symbols),
            }
            for n in res.data.get("news", [])
        ]
