"""Termine für Quartalszahlen (öffentlicher Nasdaq-Kalender). Ohne Verbindung: keine Termine."""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import date, timedelta

log = logging.getLogger(__name__)
URL = "https://api.nasdaq.com/api/calendar/earnings?date={}"
HEADERS = {"User-Agent": "Mozilla/5.0 (tradingbot)", "Accept": "application/json"}


def fetch_day(day: date) -> list[str]:
    req = urllib.request.Request(URL.format(day.isoformat()), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    rows = (data.get("data") or {}).get("rows") or []
    return [row["symbol"].upper() for row in rows if row.get("symbol")]


class EarningsCalendar:
    """Merkt sich einmal am Tag, welche Aktien der Watchlist in den nächsten Tagen Zahlen melden."""

    def __init__(self, storage, fetch=fetch_day):
        self.storage, self.fetch = storage, fetch

    def upcoming(self, symbols: list[str], today: date, days: int) -> dict[str, date]:
        if days <= 0:
            return {}
        key = f"earnings_{today.isoformat()}_{days}"
        cached = self.storage.get(key)
        if cached is not None:
            return {s: date.fromisoformat(d) for s, d in json.loads(cached).items()}
        found: dict[str, date] = {}
        try:
            for i in range(days + 1):
                d = today + timedelta(days=i)
                for sym in self.fetch(d):
                    if sym in symbols and sym not in found:
                        found[sym] = d
        except Exception as e:  # Kalender ist ein Zusatz: ohne ihn läuft der Bot normal weiter
            log.warning("Termine für Quartalszahlen nicht abrufbar: %s", e)
            return {}
        self.storage.set(key, json.dumps({s: d.isoformat() for s, d in found.items()}))
        if found:
            log.info("Quartalszahlen demnächst: %s", ", ".join(f"{s} {d:%d.%m.}" for s, d in sorted(found.items())))
        return found
