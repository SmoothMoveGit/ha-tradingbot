"""Nachrichten sammeln (Alpaca + RSS), Firmen zuordnen und bewerten."""
from __future__ import annotations

import calendar
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from .sentiment import SentimentEngine

log = logging.getLogger(__name__)
MARKET = "_MARKET"  # Pseudo-Symbol für allgemeine Welt- und Marktnachrichten


def fetch_rss(feeds: list[str], since: datetime) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        return []
    items = []
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            log.warning("RSS %s nicht lesbar: %s", url, e)
            continue
        if parsed.get("bozo") and not parsed.entries:
            log.warning("RSS %s liefert nichts: %s", url, parsed.get("bozo_exception"))
            continue
        for e in parsed.entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            t = datetime.fromtimestamp(calendar.timegm(ts), timezone.utc) if ts else datetime.now(timezone.utc)
            if t < since:
                continue
            key = e.get("id") or e.get("link") or e.get("title", "")
            items.append({
                "id": "rss-" + hashlib.sha1(key.encode()).hexdigest()[:16],
                "time": t,
                "headline": e.get("title", ""),
                "summary": e.get("summary", "")[:500],
                "source": parsed.feed.get("title", url),
                "url": e.get("link"),
                "symbols": [],
            })
    return items


def tag_symbols(item: dict, watchlist: list[str], aliases: dict[str, list[str]]) -> list[str]:
    """Ordnet eine Nachricht Aktien zu (über Ticker oder Firmennamen). Ohne Treffer: Gesamtmarkt."""
    syms = [s for s in item.get("symbols", []) if s in watchlist]
    text = f" {item['headline']} {item.get('summary', '')} ".lower()
    for sym in watchlist:
        if sym in syms:
            continue
        names = aliases.get(sym, []) + [sym]
        if any(f" {n.lower()}" in text for n in names):
            syms.append(sym)
    return syms or [MARKET]


class NewsAnalyzer:
    def __init__(self, cfg, storage, broker):
        self.cfg, self.storage, self.broker = cfg, storage, broker
        self.engine = SentimentEngine(cfg.news.sentiment_engine, cfg.news.claude_model)

    def refresh(self) -> int:
        """Neue Nachrichten holen, bewerten, speichern. Gibt Anzahl neuer Artikel zurück."""
        since = datetime.now(timezone.utc) - timedelta(hours=self.cfg.strategy.news_lookback_hours)
        items: list[dict] = []
        if self.cfg.news.use_alpaca_news:
            items += self.broker.fetch_news(self.cfg.watchlist, since)
        items += fetch_rss(self.cfg.news.rss_feeds, since)
        new = [i for i in items if not self.storage.has_news(i["id"])]
        scores = self.engine.score_many([f"{i['headline']}. {i['summary']}" for i in new])
        for item, score in zip(new, scores):
            for sym in tag_symbols(item, self.cfg.watchlist, self.cfg.aliases):
                self.storage.add_news(item, sym, score)
        if new:
            log.info("%d neue Nachrichten bewertet", len(new))
        return len(new)

    def score(self, symbol: str, now: datetime | None = None) -> float:
        """Zeitlich gewichtete Stimmung (neuere Nachrichten zählen mehr). -1..1."""
        now = now or datetime.now(timezone.utc)
        since = now - timedelta(hours=self.cfg.strategy.news_lookback_hours)
        half_life = self.cfg.strategy.news_half_life_hours
        num = den = 0.0
        for t, s in self.storage.news_scores(symbol, since):
            age_h = max(0.0, (now - t).total_seconds() / 3600)
            w = 0.5 ** (age_h / half_life)
            num += w * s
            den += w
        # Wenige Artikel -> Wert Richtung 0 ziehen (Vertrauen wächst mit Menge)
        return num / (den + 0.5) if den else 0.0

    def latest_shock(self, symbol: str, hours: float = 2.0) -> float:
        """Schlechteste Bewertung der letzten Stunden (für Panik-Verkauf)."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return min((s for _, s in self.storage.news_scores(symbol, since)), default=0.0)
