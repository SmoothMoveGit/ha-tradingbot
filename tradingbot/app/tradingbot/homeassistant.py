"""Meldet den Zustand des Bots an Home Assistant (Sensoren + Push-Nachrichten)."""
from __future__ import annotations

import json
import logging
import os
import urllib.request

log = logging.getLogger(__name__)


class Reporter:
    """Standard: meldet nichts. Wird ersetzt, wenn der Bot als Home-Assistant-Add-on läuft."""

    def publish(self, status: dict) -> None: ...

    def notify(self, title: str, message: str) -> None: ...

    def publish_daytrader(self, status: dict) -> None: ...


class HomeAssistantReporter(Reporter):
    def __init__(self, url: str, token: str, notify_service: str = ""):
        self.url = url.rstrip("/")
        self.token = token
        self.notify_service = notify_service.strip()

    @classmethod
    def from_env(cls) -> Reporter:
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token:
            return Reporter()
        return cls("http://supervisor/core/api", token, os.getenv("TRADINGBOT_NOTIFY_SERVICE", ""))

    def _post(self, path: str, data: dict) -> None:
        req = urllib.request.Request(
            f"{self.url}{path}",
            data=json.dumps(data).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10).close()
        except Exception as e:  # Home Assistant darf den Bot nie aufhalten
            log.warning("Home Assistant nicht erreichbar (%s): %s", path, e)

    def _state(self, entity_id: str, state, **attrs) -> None:
        self._post(f"/states/{entity_id}", {"state": state, "attributes": attrs})

    def publish(self, s: dict) -> None:
        money = {"unit_of_measurement": "USD", "device_class": "monetary", "state_class": "total"}
        self._state("sensor.tradingbot_wert", round(s["value"], 2), friendly_name="Tradingbot Wert",
                    icon="mdi:chart-line", **money)
        self._state("sensor.tradingbot_kapital", round(s["capital"], 2), friendly_name="Tradingbot Kapital",
                    icon="mdi:cash", **money)
        self._state("sensor.tradingbot_gewinn", round(s["realized_pnl"], 2),
                    friendly_name="Tradingbot realisierter Gewinn", icon="mdi:cash-plus", **money)
        if s.get("benchmark_value") is not None:
            self._state("sensor.tradingbot_vergleich_etf", round(s["benchmark_value"], 2),
                        friendly_name=f"Tradingbot Vergleich {s.get('benchmark') or 'ETF'}", icon="mdi:scale-balance",
                        vorsprung=round(s["value"] - s["benchmark_value"], 2), **money)
        self._state("sensor.tradingbot_positionen", len(s["positions"]), friendly_name="Tradingbot Positionen",
                    icon="mdi:briefcase", aktien=s["positions"], details=s.get("positions_detail", []),
                    max_positionen=s.get("max_positions"))
        self._state("sensor.tradingbot_status", s["status"], friendly_name="Tradingbot Status",
                    icon="mdi:robot", modus=s["mode"], letzter_trade=s.get("last_trade"),
                    strategie=s.get("strategy"), watchlist=s.get("watchlist"),
                    intervall_minuten=s.get("interval_minutes"), letzter_lauf=s.get("last_run"))
        self._state("binary_sensor.tradingbot_not_aus", "on" if s["halted"] else "off",
                    friendly_name="Tradingbot Not-Aus", device_class="problem")
        if "positions_detail" in s:
            self._publish_details(s, money)

    def _publish_details(self, s: dict, money: dict) -> None:
        pct = {"unit_of_measurement": "%", "state_class": "measurement"}
        self._state("sensor.tradingbot_unrealisiert", round(s["unrealized_pnl"], 2),
                    friendly_name="Tradingbot offener Gewinn", icon="mdi:chart-areaspline", **money)
        self._state("sensor.tradingbot_bargeld", round(s["cash"], 2), friendly_name="Tradingbot Bargeld",
                    icon="mdi:wallet", investiert=round(s["invested"], 2), **money)
        paid = s["paid_in"]
        self._state("sensor.tradingbot_rendite", round((s["value"] / paid - 1) * 100, 2) if paid else 0.0,
                    friendly_name="Tradingbot Rendite", icon="mdi:percent", eingezahlt=round(paid, 2), **pct)
        self._state("sensor.tradingbot_heute", round(s["day_change_pct"], 2), friendly_name="Tradingbot heute",
                    icon="mdi:calendar-today", tageslimit_prozent=s["daily_loss_limit_pct"], **pct)
        self._state("sensor.tradingbot_drawdown", round(s["drawdown_pct"], 2),
                    friendly_name="Tradingbot Abstand zum Höchststand", icon="mdi:trending-down",
                    hoechststand=round(s["peak_value"], 2), not_aus_bei_prozent=s["max_drawdown_pct"],
                    stop_loss_prozent=s["stop_loss_pct"], trailing_stop_prozent=s["trailing_stop_pct"],
                    gewinnmitnahme_prozent=s["take_profit_pct"], **pct)
        m = s["market_sentiment"]
        self._state("sensor.tradingbot_marktstimmung", round(m, 2), friendly_name="Tradingbot Marktstimmung",
                    icon="mdi:earth", state_class="measurement",
                    bewertung="positiv" if m > 0.15 else "negativ" if m < -0.15 else "neutral",
                    aktien=s["news_scores"], signale=s["signals"], schlagzeilen=s["news"])
        self._state("sensor.tradingbot_trades", s["trade_count"], friendly_name="Tradingbot Trades",
                    icon="mdi:swap-horizontal", state_class="total", letzte=s["trades"])

    def publish_daytrader(self, s: dict) -> None:
        money = {"unit_of_measurement": "USD", "device_class": "monetary", "state_class": "total"}
        self._state("sensor.daytrader_wert", round(s["value"], 2), friendly_name="Daytrader Wert",
                    icon="mdi:lightning-bolt", startbudget=s["start_budget"],
                    rendite_prozent=round((s["value"] / s["start_budget"] - 1) * 100, 2), **money)
        self._state("sensor.daytrader_gewinn", round(s["realized_pnl"], 2),
                    friendly_name="Daytrader realisierter Gewinn", icon="mdi:cash-plus", **money)
        self._state("sensor.daytrader_positionen", len(s["positions"]), friendly_name="Daytrader Positionen",
                    icon="mdi:briefcase", aktien=s["positions"])
        self._state("sensor.daytrader_status", s["status"], friendly_name="Daytrader Status", icon="mdi:robot")
        self._state("sensor.daytrader_trades", s["trade_count"], friendly_name="Daytrader Trades",
                    icon="mdi:swap-horizontal", state_class="total", letzte=s["trades"])

    def notify(self, title: str, message: str) -> None:
        if self.notify_service:
            domain, _, service = self.notify_service.partition(".")
            if not service:
                domain, service = "notify", domain
            self._post(f"/services/{domain}/{service}", {"title": title, "message": message})
        else:
            self._post("/services/persistent_notification/create", {"title": title, "message": message})
