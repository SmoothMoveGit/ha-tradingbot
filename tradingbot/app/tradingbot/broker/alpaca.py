"""Alpaca-Anbindung (Paper oder Live). Unterstützt Bruchteilsaktien über Betragsorders."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest, StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest, StopOrderRequest

from .base import Account, Bar, Broker, Fill, Position

log = logging.getLogger(__name__)


class AlpacaBroker(Broker):
    def __init__(self, key: str | None, secret: str | None, paper: bool = True):
        if not key or not secret:
            raise SystemExit("Alpaca-Schlüssel fehlen: in der Add-on-Konfiguration bzw. in .env eintragen.")
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

    def history(self, symbols: list[str], start: datetime) -> dict[str, list[Bar]]:
        """Tageskurse seit start, um Aktiensplits bereinigt (für den Backtest)."""
        req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start,
                               feed=DataFeed.IEX, adjustment=Adjustment.ALL)
        data = self.data.get_stock_bars(req).data
        return {s: [Bar(b.timestamp, b.open, b.high, b.low, b.close, b.volume) for b in data.get(s, [])]
                for s in symbols}

    def last_price(self, symbol: str) -> float:
        req = StockLatestTradeRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
        return float(self.data.get_stock_latest_trade(req)[symbol].price)

    def market_open(self) -> bool:
        return bool(self.trading.get_clock().is_open)

    def minutes_to_close(self, now: datetime | None = None) -> float:
        clock = self.trading.get_clock()
        return (clock.next_close - (now or clock.timestamp)).total_seconds() / 60

    def intraday_bars(self, symbols: list[str], now: datetime | None = None, days: int = 0) -> dict[str, list[Bar]]:
        """5-Minuten-Kerzen ab Handelsbeginn heute (bzw. der letzten `days` Tage für den Backtest)."""
        from zoneinfo import ZoneInfo
        from alpaca.data.timeframe import TimeFrameUnit
        ny = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
        start = ny.replace(hour=9, minute=30, second=0, microsecond=0) - timedelta(days=days)
        req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                               start=start, feed=DataFeed.IEX)
        data = self.data.get_stock_bars(req).data
        return {s: [Bar(b.timestamp, b.open, b.high, b.low, b.close, b.volume) for b in data.get(s, [])]
                for s in symbols}

    def _wait_fill(self, order_id, timeout: float = 30.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            o = self.trading.get_order_by_id(order_id)
            if o.status in ("filled", "canceled", "rejected", "expired"):
                return o
            time.sleep(1)
        return self.trading.get_order_by_id(order_id)

    def buy_notional(self, symbol: str, amount: float) -> Fill | None:
        # Alpaca lehnt Käufe ab, solange eine Verkaufs-Stop-Order offen ist ("wash trade").
        # Beim Nachkauf daher erst den Stop entfernen, der Bot setzt ihn danach neu.
        if any(o.side == OrderSide.SELL for o in self._open_orders(symbol)):
            self._cancel_open(symbol)
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

    def _open_orders(self, symbol: str):
        return self.trading.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))

    def _cancel_open(self, symbol: str) -> None:
        for o in self._open_orders(symbol):
            try:
                self.trading.cancel_order_by_id(o.id)
            except APIError as e:
                log.warning("Order %s für %s nicht stornierbar: %s", o.id, symbol, e)
        time.sleep(1)  # Alpaca gibt die Stückzahl erst nach der Stornierung frei

    def ensure_stop(self, symbol: str, qty: float, stop_price: float) -> None:
        """Hält genau eine Stop-Order beim Broker aktuell. Gültig bis Handelsschluss, wird täglich erneuert."""
        stop_price = round(stop_price, 2)
        stops = [o for o in self._open_orders(symbol) if o.type == OrderType.STOP]
        same_qty = stops and any(abs(float(stops[0].qty or 0) - q) < 1e-6 for q in (round(qty, 9), float(int(qty))))
        if stops and same_qty and abs(float(stops[0].stop_price) - stop_price) / stop_price < 0.005:
            return
        if stops:
            self._cancel_open(symbol)
        for q in (round(qty, 9), float(int(qty))):  # Bruchteile, sonst nur ganze Stücke
            if q <= 0:
                continue
            req = StopOrderRequest(symbol=symbol, qty=q, side=OrderSide.SELL,
                                   time_in_force=TimeInForce.DAY, stop_price=stop_price)
            try:
                self.trading.submit_order(req)
                log.info("Stop-Order bei Alpaca: %s %.4f Stück, Stopp bei %.2f", symbol, q, stop_price)
                return
            except APIError as e:
                log.warning("Stop-Order %s (%.4f Stück) abgelehnt: %s", symbol, q, e)
        log.warning("Kein Stop beim Broker für %s, der Bot überwacht selbst", symbol)

    def last_sell_fill(self, symbol: str, since: datetime | None = None) -> Fill | None:
        orders = self.trading.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.CLOSED, symbols=[symbol], side=OrderSide.SELL, limit=5, after=since))
        filled = [o for o in orders if o.filled_qty and float(o.filled_qty) > 0]
        if not filled:
            return None
        o = filled[0]
        return Fill(symbol, "sell", float(o.filled_qty), float(o.filled_avg_price))

    def sell_qty(self, symbol: str, qty: float) -> Fill | None:
        self._cancel_open(symbol)  # Stop-Order blockiert sonst die Stückzahl
        req = MarketOrderRequest(
            symbol=symbol, qty=round(qty, 6), side=OrderSide.SELL, time_in_force=TimeInForce.DAY
        )
        try:
            o = self._wait_fill(self.trading.submit_order(req).id)
        except APIError as e:
            log.error("Teilverkauf %s abgelehnt: %s", symbol, e)
            return None
        if not o.filled_qty or float(o.filled_qty) == 0:
            log.warning("Teilverkauf %s nicht ausgeführt (Status %s)", symbol, o.status)
            return None
        return Fill(symbol, "sell", float(o.filled_qty), float(o.filled_avg_price))

    def sell_all(self, symbol: str) -> Fill | None:
        self._cancel_open(symbol)
        try:
            o = self._wait_fill(self.trading.close_position(symbol).id)
        except APIError as e:
            log.error("Verkauf %s fehlgeschlagen: %s", symbol, e)
            return None
        if not o.filled_qty or float(o.filled_qty) == 0:
            return None
        return Fill(symbol, "sell", float(o.filled_qty), float(o.filled_avg_price))

    def fetch_news(self, symbols: list[str], since: datetime, limit: int = 500) -> list[dict]:
        try:
            res = self.news.get_news(NewsRequest(symbols=",".join(symbols), start=since, limit=limit))
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
