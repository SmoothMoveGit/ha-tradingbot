"""Kommandozeile: python -m tradingbot [run|once|status|sim|reset-halt]"""
from __future__ import annotations

import argparse
import logging
import sys

from .broker import make_broker
from .config import load_config, load_env_file
from .storage import Storage


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tradingbot", description="Autonomer Aktien-Tradingbot")
    p.add_argument("command", choices=["run", "once", "status", "sim", "reset-halt"])
    p.add_argument("-c", "--config", default="config.yaml")
    p.add_argument("--days", type=int, default=90, help="Tage für 'sim'")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    load_env_file()
    cfg = load_config(args.config)

    if args.command == "status":
        return status(cfg)
    if args.command == "reset-halt":
        from .risk import RiskManager
        RiskManager(cfg, Storage(cfg.db_path)).reset_halt()
        print("Not-Aus zurückgesetzt.")
        return 0
    if args.command == "sim":
        return simulate(cfg, args.days)

    from .bot import TradingBot
    if cfg.mode == "live":
        logging.warning("ACHTUNG: LIVE-MODUS MIT ECHTEM GELD")
    from .homeassistant import HomeAssistantReporter
    bot = TradingBot(cfg, make_broker(cfg), reporter=HomeAssistantReporter.from_env())
    if args.command == "once":
        bot.run_cycle()
    else:
        bot.run_forever()
    return 0


def status(cfg) -> int:
    from .risk import RiskManager
    st = Storage(cfg.db_path)
    risk = RiskManager(cfg, st)
    print(f"Modus: {cfg.mode} | Startbudget: {cfg.risk.start_budget:.2f} | Kapital jetzt: {risk.bot_capital():.2f}")
    print(f"Realisierter Gewinn/Verlust: {st.realized_pnl():+.2f} | Not-Aus aktiv: {'ja' if risk.halted else 'nein'}")
    print("Offene Positionen (Einstand):", st.all_meta() or "keine")
    print("\nLetzte Trades:")
    for t, sym, side, qty, price, pnl, reason in st.recent_trades():
        print(f"  {t[:16]} {side:4} {sym:6} {qty:9.4f} @ {price:8.2f}  G/V {pnl:+8.2f}  {reason}")
    print("\nLetzte Nachrichten:")
    for t, sym, score, headline in st.recent_news():
        print(f"  {t[:16]} {sym:8} {score:+.2f}  {headline[:90]}")
    return 0


def simulate(cfg, days: int) -> int:
    """Trockenlauf ohne Internet mit simulierten Kursen."""
    from .bot import TradingBot
    from .broker.sim import SimBroker
    cfg.news.use_alpaca_news = False
    cfg.news.rss_feeds = []
    broker = SimBroker(cfg.risk.start_budget, cfg.watchlist)
    bot = TradingBot(cfg, broker, Storage(":memory:"))
    logging.getLogger("tradingbot.bot").setLevel(logging.WARNING)
    from datetime import date, timedelta
    day = date.today()
    for i in range(days):
        broker.step(1)
        bot.run_cycle(today=day + timedelta(days=i))
    acct = broker.account()
    print(f"Simulation über {days} Tage: Startbudget {cfg.risk.start_budget:.2f} -> Depotwert {acct.equity:.2f} "
          f"({acct.equity / cfg.risk.start_budget - 1:+.1%}), {len(bot.storage.recent_trades(10_000))} Trades")
    print("Hinweis: Zufallskurse, sagt nichts über echte Gewinne aus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
