"""Nachrichten sammeln (Alpaca + RSS), Firmen zuordnen und bewerten."""
from __future__ import annotations

import calendar
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

from .sentiment import SentimentEngine

log = logging.getLogger(__name__)
WORDS = re.compile(r"[a-zäöüß0-9]+")
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


# Wörter, an denen man Wirtschafts- und Weltlage-Meldungen erkennt (für allgemeine RSS-Feeds)
MARKET_WORDS = {
    "market", "markets", "stock", "stocks", "shares", "economy", "economic", "fed", "rate", "rates",
    "inflation", "recession", "tariff", "tariffs", "trade", "sanctions", "war", "oil", "bank", "banks",
    "earnings", "gdp", "jobs", "unemployment", "dollar", "bond", "bonds", "treasury", "crisis", "chip",
    "chips", "ai", "regulation", "antitrust", "strike", "supply", "china", "election", "default",
    "börse", "aktien", "wirtschaft", "konjunktur", "zinsen", "zins", "inflation", "zölle", "krieg",
    "rezession", "ezb", "dax", "ölpreis", "handel", "export", "insolvenz", "arbeitsmarkt",
}


def _norm_headline(text: str) -> str:
    return " ".join(WORDS.findall(text.lower()))[:120]


def is_relevant(item: dict, watchlist: list[str], aliases: dict[str, list[str]], related: dict[str, list[str]]) -> bool:
    """Lohnt sich die Bewertung? Firmenmeldungen immer, allgemeine Meldungen nur mit Wirtschaftsbezug."""
    if item.get("symbols"):
        return True
    if tag_symbols(item, watchlist, aliases) != [MARKET]:
        return True
    words = set(WORDS.findall(f"{item['headline']} {item.get('summary', '')}".lower()))
    partners = {p.lower() for s in watchlist for p in related.get(s, [])}
    return bool(words & (MARKET_WORDS | partners))


def related_symbols(item: dict, watchlist: list[str], related: dict[str, list[str]]) -> list[str]:
    """Watchlist-Aktien, deren Partnerfirma (Zulieferer, Kunde, Konkurrent) in der Nachricht vorkommt."""
    tagged = set(item.get("symbols", []))
    return [sym for sym in watchlist if sym not in tagged and tagged & set(related.get(sym, []))]


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
        log.info("Nachrichtenbewertung: %s", "Claude (" + self.engine.model + ")" if self.engine.engine == "claude" else "Lexikon")

    def refresh(self) -> int:
        """Neue Nachrichten holen, bewerten, speichern. Gibt Anzahl neuer Artikel zurück."""
        since = datetime.now(timezone.utc) - timedelta(hours=self.cfg.strategy.news_lookback_hours)
        wl, related = self.cfg.watchlist, self.cfg.related
        items: list[dict] = []
        if self.cfg.news.use_alpaca_news:
            partners = sorted({p for s in wl for p in related.get(s, [])} - set(wl))
            items += self.broker.fetch_news(wl + partners, since, self.cfg.news.max_alpaca_news)
        items += fetch_rss(self.cfg.news.rss_feeds, since)
        new, seen = [], set()
        for i in items:  # gleiche Meldung aus mehreren Quellen nur einmal, Unwichtiges gar nicht bewerten
            key = _norm_headline(i["headline"])
            if i["id"] in seen or key in seen or self.storage.has_news(i["id"]):
                continue
            seen.update((i["id"], key))
            if is_relevant(i, wl, self.cfg.aliases, related):
                new.append(i)
        texts = [f"{i['headline']}. {i['summary']}" for i in new]
        companies = {s: (self.cfg.aliases.get(s) or [s])[0] for s in wl}
        impacts = self.engine.impacts_many(texts, companies, related, MARKET)
        if impacts is None:  # Lexikon: direkt genannte Firmen voll, Partnerfirmen abgeschwächt
            impacts = []
            for item, score in zip(new, self.engine.score_many(texts)):
                effects = {s: score for s in tag_symbols(item, wl, self.cfg.aliases)}
                for s in related_symbols(item, wl, related):
                    effects.setdefault(s, score * self.cfg.news.related_weight)
                if MARKET in effects and len(effects) > 1:
                    del effects[MARKET]
                impacts.append(effects)
        for item, effects in zip(new, impacts):
            firms = {s: v for s, v in effects.items() if s != MARKET and v}
            for sym, score in firms.items():
                self.storage.add_news(item, sym, score)
            market = effects.get(MARKET, 0.0)
            if not firms or abs(market) >= 0.5:  # reine Weltnachricht oder großes Ereignis
                self.storage.add_news(item, MARKET, market)
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
