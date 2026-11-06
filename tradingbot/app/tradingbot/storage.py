"""SQLite-Speicher für Nachrichten, Trades, Kontostand und Bot-Zustand."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS news (
    id TEXT, symbol TEXT, time TEXT, headline TEXT, source TEXT, url TEXT, score REAL,
    PRIMARY KEY (id, symbol));
CREATE INDEX IF NOT EXISTS news_symbol_time ON news(symbol, time);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, symbol TEXT, side TEXT,
    qty REAL, price REAL, reason TEXT, pnl REAL);
CREATE TABLE IF NOT EXISTS positions_meta (symbol TEXT PRIMARY KEY, cost REAL, high REAL, opened TEXT);
CREATE TABLE IF NOT EXISTS equity (time TEXT, bot_value REAL, bot_capital REAL, account_equity REAL);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat()


class Storage:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    # Nachrichten
    def has_news(self, news_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM news WHERE id=? LIMIT 1", (news_id,)).fetchone() is not None

    def add_news(self, item: dict, symbol: str, score: float) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO news VALUES (?,?,?,?,?,?,?)",
            (item["id"], symbol, _iso(item["time"]), item["headline"], item.get("source"), item.get("url"), score),
        )
        self.db.commit()

    def news_scores(self, symbol: str, since: datetime) -> list[tuple[datetime, float]]:
        rows = self.db.execute(
            "SELECT time, score FROM news WHERE symbol=? AND time>=?", (symbol, _iso(since))
        ).fetchall()
        return [(datetime.fromisoformat(t), s) for t, s in rows]

    def recent_news(self, limit: int = 10):
        return self.db.execute(
            "SELECT time, symbol, score, headline FROM news ORDER BY time DESC LIMIT ?", (limit,)
        ).fetchall()

    # Trades und Positionen
    def record_trade(self, symbol, side, qty, price, reason, pnl=0.0, when: datetime | None = None) -> None:
        self.db.execute(
            "INSERT INTO trades (time,symbol,side,qty,price,reason,pnl) VALUES (?,?,?,?,?,?,?)",
            (_iso(when or datetime.now(timezone.utc)), symbol, side, qty, price, reason, pnl),
        )
        self.db.commit()

    def realized_pnl(self) -> float:
        return self.db.execute("SELECT COALESCE(SUM(pnl),0) FROM trades").fetchone()[0]

    def recent_trades(self, limit: int = 10):
        return self.db.execute(
            "SELECT time, symbol, side, qty, price, pnl, reason FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def trade_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

    def open_meta(self, symbol: str, cost: float, price: float, when: datetime | None = None) -> None:
        row = self.get_meta(symbol)
        if row:
            self.db.execute("UPDATE positions_meta SET cost=cost+? WHERE symbol=?", (cost, symbol))
        else:
            self.db.execute(
                "INSERT INTO positions_meta VALUES (?,?,?,?)",
                (symbol, cost, price, _iso(when or datetime.now(timezone.utc))),
            )
        self.db.commit()

    def get_meta(self, symbol: str):
        return self.db.execute("SELECT cost, high, opened FROM positions_meta WHERE symbol=?", (symbol,)).fetchone()

    def all_meta(self) -> dict[str, float]:
        return dict(self.db.execute("SELECT symbol, cost FROM positions_meta").fetchall())

    def update_high(self, symbol: str, price: float) -> float:
        self.db.execute("UPDATE positions_meta SET high=MAX(high, ?) WHERE symbol=?", (price, symbol))
        self.db.commit()
        row = self.get_meta(symbol)
        return row[1] if row else price

    def reduce_meta(self, symbol: str, fraction: float) -> None:
        """Einstand nach einem Teilverkauf anteilig senken."""
        self.db.execute("UPDATE positions_meta SET cost=cost*? WHERE symbol=?", (max(0.0, 1 - fraction), symbol))
        self.db.commit()

    def close_meta(self, symbol: str) -> None:
        self.db.execute("DELETE FROM positions_meta WHERE symbol=?", (symbol,))
        self.db.commit()

    # Zustand
    def get(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set(self, key: str, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, str(value)))
        self.db.commit()

    def record_equity(self, bot_value: float, bot_capital: float, account_equity: float) -> None:
        self.db.execute(
            "INSERT INTO equity VALUES (?,?,?,?)",
            (_iso(datetime.now(timezone.utc)), bot_value, bot_capital, account_equity),
        )
        self.db.commit()
