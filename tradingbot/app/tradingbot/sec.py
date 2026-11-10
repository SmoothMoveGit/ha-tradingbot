"""Pflichtmeldungen (Formular 8-K) der US-Börsenaufsicht SEC als zusätzliche Nachrichtenquelle.

Idee und Feed-Aufbau nach trader-news/news.py aus github.com/Jakeschincariol/day-trader-skill (MIT-Lizenz).
Die SEC verlangt einen User-Agent mit Name und Kontakt und höchstens 10 Anfragen pro Sekunde.
"""
from __future__ import annotations

import gzip
import json
import logging
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FEED_URL = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=8-K"
            "&dateb=&owner=include&count=10&output=atom")

ITEMS = {
    "1.03": "Insolvenz", "1.05": "Cyberangriff", "2.06": "Abschreibung", "3.01": "Delisting-Warnung",
    "4.02": "frühere Zahlen unzuverlässig", "5.02": "Wechsel im Vorstand",
}
HARD_ITEMS = {"1.03", "3.01", "4.02"}    # sofort verkaufen und Kaufsperre
REVIEW_ITEMS = {"1.05", "2.06", "5.02"}  # an die normale Nachrichtenbewertung (Claude)
BLOCK_DAYS = 30
FETCH_EVERY = timedelta(minutes=30)
CIK_MAX_AGE = timedelta(days=7)


def valid_user_agent(ua: str) -> bool:
    return "@" in (ua or "") and len(ua.strip()) > 5


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(el, name: str) -> str:
    for c in el.iter():
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def _time(value: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def parse_atom(data: bytes, symbol: str) -> list[dict]:
    """EDGAR-Atom-Feed einer Firma -> nur die wichtigen 8-K-Meldungen als Nachrichten."""
    root = ET.fromstring(data)
    out = []
    for entry in root.iter():
        if _local(entry.tag) != "entry":
            continue
        items = sorted(set(re.findall(r"\d+\.\d+", _text(entry, "items-desc"))) & (HARD_ITEMS | REVIEW_ITEMS))
        when = _time(_text(entry, "updated"))
        acc = _text(entry, "accession-number")
        if not items or not when or not acc:
            continue
        link = next((c.get("href", "") for c in entry.iter() if _local(c.tag) == "link"), "")
        labels = ", ".join(ITEMS[i] for i in items)
        out.append({
            "id": f"sec-{acc}", "time": when, "source": "SEC EDGAR", "url": link, "symbols": [symbol],
            "headline": f"{symbol} SEC filing 8-K: {labels}",
            "summary": f"Pflichtmeldung an die SEC (Formular 8-K), Punkte {', '.join(items)}: {labels}.",
            "sec_items": items, "hard": bool(set(items) & HARD_ITEMS), "label": labels,
        })
    return out


class SecFilings:
    def __init__(self, user_agent: str, storage, pause: float = 0.25):
        self.ua, self.storage, self.pause = user_agent.strip(), storage, pause
        self._last_request = 0.0
        self._last_fetch: datetime | None = None

    def _get(self, url: str) -> bytes:
        wait = self.pause - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
            return gzip.decompress(data) if r.headers.get("Content-Encoding") == "gzip" else data

    def ciks(self) -> dict[str, str]:
        cached = json.loads(self.storage.get("sec_ciks", "{}") or "{}")
        fetched = self.storage.get("sec_ciks_at")
        if cached and fetched and datetime.now(timezone.utc) - datetime.fromisoformat(fetched) < CIK_MAX_AGE:
            return cached
        data = json.loads(self._get(TICKERS_URL))
        ciks = {v["ticker"].upper().replace("-", "."): str(v["cik_str"]).zfill(10) for v in data.values()}
        self.storage.set("sec_ciks", json.dumps(ciks))
        self.storage.set("sec_ciks_at", datetime.now(timezone.utc).isoformat())
        return ciks

    def fetch(self, symbols: list[str], since: datetime, now: datetime | None = None) -> list[dict]:
        """Neue wichtige 8-K-Meldungen seit `since`. Fragt höchstens alle 30 Minuten bei der SEC an."""
        now = now or datetime.now(timezone.utc)
        if self._last_fetch and now - self._last_fetch < FETCH_EVERY:
            return []
        self._last_fetch = now
        try:
            ciks = self.ciks()
        except Exception as e:
            log.warning("SEC-Firmenliste nicht abrufbar: %s", e)
            return []
        out, failed, checked = [], [], 0
        for sym in symbols:
            cik = ciks.get(sym)
            if not cik:
                continue
            try:
                out += [f for f in parse_atom(self._get(FEED_URL.format(cik=cik)), sym) if f["time"] >= since]
                checked += 1
            except Exception as e:
                failed.append(f"{sym} ({e})")
        log.info("SEC: %d Firmen geprüft, %d wichtige 8-K-Meldungen%s", checked, len(out),
                 f" ({', '.join(f['symbols'][0] + ': ' + f['label'] for f in out)})" if out else "")
        if failed:
            log.warning("SEC-Meldungen nicht abrufbar für %s", ", ".join(failed))
        return out


def block(storage, symbol: str, label: str, when: date) -> None:
    storage.set(f"sec_block:{symbol}", json.dumps({"date": when.isoformat(), "label": label}))


def blocked(storage, symbol: str, today: date) -> str | None:
    """Grund der Kaufsperre nach einer schweren SEC-Meldung, sonst None."""
    raw = storage.get(f"sec_block:{symbol}")
    if not raw:
        return None
    b = json.loads(raw)
    if (today - date.fromisoformat(b["date"])).days >= BLOCK_DAYS:
        return None
    return b["label"]
