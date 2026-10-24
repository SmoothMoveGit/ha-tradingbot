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
                    icon="mdi:briefcase", aktien=s["positions"])
        self._state("sensor.tradingbot_status", s["status"], friendly_name="Tradingbot Status",
                    icon="mdi:robot", modus=s["mode"], letzter_trade=s.get("last_trade"))
        self._state("binary_sensor.tradingbot_not_aus", "on" if s["halted"] else "off",
                    friendly_name="Tradingbot Not-Aus", device_class="problem")

    def notify(self, title: str, message: str) -> None:
        if self.notify_service:
            domain, _, service = self.notify_service.partition(".")
            if not service:
                domain, service = "notify", domain
            self._post(f"/services/{domain}/{service}", {"title": title, "message": message})
        else:
            self._post("/services/persistent_notification/create", {"title": title, "message": message})
