"""Konfiguration aus YAML-Datei plus Umgebungsvariablen (Secrets nur per .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RiskConfig:
    start_budget: float = 300.0           # Guthaben, mit dem der Bot startet (USD)
    reinvest_profits: bool = True         # realisierte Gewinne dürfen wieder eingesetzt werden
    max_position_pct: float = 0.20        # max. Anteil des Bot-Kapitals pro Aktie
    max_positions: int = 4
    min_cash_reserve_pct: float = 0.10    # immer so viel Cash zurückhalten
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.12
    trailing_stop_pct: float = 0.06       # Verkauf, wenn Kurs so weit vom Hoch seit Kauf fällt
    daily_loss_limit_pct: float = 0.03    # Not-Aus für den Tag
    max_drawdown_pct: float = 0.25        # Not-Aus dauerhaft (manuell zurücksetzen)
    min_order_value: float = 10.0
    rebuy_cooldown_days: int = 2          # nach Verkauf diese Aktie so lange nicht wieder kaufen
    broker_stops: bool = True             # Stop-Order zusätzlich beim Broker hinterlegen


@dataclass
class StrategyConfig:
    sma_fast: int = 10
    sma_slow: int = 30
    trend_weight: float = 0.6
    news_weight: float = 0.4
    buy_threshold: float = 0.35
    sell_threshold: float = -0.25
    panic_news_threshold: float = -0.6    # sehr schlechte Nachricht -> sofort verkaufen
    news_lookback_hours: int = 24
    news_half_life_hours: float = 6.0
    market_news_weight: float = 0.3       # Einfluss allgemeiner Weltnachrichten


@dataclass
class NewsConfig:
    use_alpaca_news: bool = True
    rss_feeds: list[str] = field(default_factory=list)
    sentiment_engine: str = "lexicon"     # "lexicon" oder "claude"
    claude_model: str = "claude-haiku-5-5"


@dataclass
class Config:
    mode: str = "paper"                   # "paper", "live" oder "sim"
    interval_minutes: int = 15
    watchlist: list[str] = field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"])
    aliases: dict[str, list[str]] = field(default_factory=dict)
    db_path: str = "data/tradingbot.db"
    benchmark: str = "SPY"                # Vergleich: einfach einen S&P-500-ETF halten
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    news: NewsConfig = field(default_factory=NewsConfig)

    # Secrets kommen ausschließlich aus der Umgebung
    @property
    def alpaca_key(self) -> str | None:
        return os.getenv("ALPACA_API_KEY")

    @property
    def alpaca_secret(self) -> str | None:
        return os.getenv("ALPACA_SECRET_KEY")

    @property
    def live_confirmed(self) -> bool:
        return os.getenv("CONFIRM_LIVE_TRADING", "").lower() == "ja-ich-kenne-das-risiko"


def _merge(dc, data: dict):
    for key, value in (data or {}).items():
        if not hasattr(dc, key):
            raise ValueError(f"Unbekannter Konfigurationsschlüssel: {key}")
        current = getattr(dc, key)
        if hasattr(current, "__dataclass_fields__"):
            _merge(current, value)
        else:
            setattr(dc, key, value)
    return dc


def load_env_file(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config(path: str | Path | None = None) -> Config:
    cfg = Config()
    if path and Path(path).exists():
        _merge(cfg, yaml.safe_load(Path(path).read_text()) or {})
    # Umgebungsvariablen haben Vorrang (z.B. aus der Home-Assistant-Add-on-Oberfläche)
    if os.getenv("TRADINGBOT_MODE"):
        cfg.mode = os.environ["TRADINGBOT_MODE"]
    if os.getenv("TRADINGBOT_START_BUDGET"):
        cfg.risk.start_budget = float(os.environ["TRADINGBOT_START_BUDGET"])
    if os.getenv("TRADINGBOT_DB_PATH"):
        cfg.db_path = os.environ["TRADINGBOT_DB_PATH"]
    if os.getenv("ANTHROPIC_API_KEY") and os.getenv("TRADINGBOT_SENTIMENT"):
        cfg.news.sentiment_engine = os.environ["TRADINGBOT_SENTIMENT"]
    if cfg.mode not in ("paper", "live", "sim"):
        raise ValueError("mode muss 'paper', 'live' oder 'sim' sein")
    if cfg.mode == "live" and not cfg.live_confirmed:
        raise SystemExit(
            "Live-Modus verweigert: setze CONFIRM_LIVE_TRADING=ja-ich-kenne-das-risiko in .env, "
            "wenn du wirklich mit echtem Geld handeln willst."
        )
    return cfg
