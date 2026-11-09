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
    p.add_argument("command", choices=["run", "once", "status", "sim", "backtest", "reset-halt", "daytrade"])
    p.add_argument("-c", "--config", default="config.yaml")
    p.add_argument("--days", type=int, default=90, help="Tage für 'sim'")
    p.add_argument("--years", type=float, default=3, help="Jahre für 'backtest'")
    p.add_argument("--variants", action="store_true", help="'backtest': mehrere Einstellungen vergleichen")
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
    if args.command == "backtest":
        return backtest(cfg, args.years, args.variants)
    if args.command == "daytrade":
        return daytrade(cfg)

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


def backtest(cfg, years: float, variants: bool = False) -> int:
    """Regeln gegen echte Alpaca-Tageskurse der letzten Jahre testen."""
    from datetime import datetime, timedelta, timezone

    from .backtest import WARMUP_DAYS, format_result, format_variants, run_backtest, run_variants
    from .broker.alpaca import AlpacaBroker
    broker = AlpacaBroker(cfg.alpaca_key, cfg.alpaca_secret, paper=True)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(365 * years))
    symbols = list(dict.fromkeys(cfg.watchlist + ([cfg.benchmark] if cfg.benchmark else [])))
    logging.getLogger(__name__).info("Backtest: lade Tageskurse für %d Werte seit %s", len(symbols), start.date())
    bars = broker.history(symbols, start - timedelta(days=WARMUP_DAYS * 1.5))
    out = logging.getLogger("tradingbot.backtest")
    for line in format_result(run_backtest(cfg, bars, start.date())):
        out.info(line)
    if variants:
        cut = (end - timedelta(days=365)).date()
        for line in format_variants(run_variants(cfg, bars, start.date(), cut, end.date())):
            out.info(line)
    return 0


def daytrade(cfg) -> int:
    """Zweiter Bot (nur Spielgeld): erst Backtest der letzten Wochen, dann Daytrading."""
    from .broker.alpaca import AlpacaBroker
    import threading
    from .daytrader import EXTRA_SYMBOLS, LOOSE, MORE_SYMBOLS, DayTrader, backtest as day_backtest, config_from_env
    from .earnings import EarningsCalendar
    from .homeassistant import HomeAssistantReporter
    # Seit 0.7.9: gelockertes Regelwerk auf 40 Werten, Ziel 1,5R, Einstand-Stop ab 1R
    # (bester Wert im 40-Tage-Vergleich vom 05.11.: +2,5 % bei 89 Trades; Michi hat Anpassungen freigegeben)
    wide = list(dict.fromkeys(cfg.watchlist + EXTRA_SYMBOLS))
    wider = list(dict.fromkeys(wide + MORE_SYMBOLS))
    exit_b = {"reward_risk": 1.5, "breakeven_r": 1.0}
    dcfg = config_from_env(wider, **LOOSE, **exit_b)
    broker = AlpacaBroker(cfg.alpaca_key, cfg.alpaca_secret, paper=True)  # Daytrader nie mit echtem Geld
    log = logging.getLogger("tradingbot.daytrader")
    def compare() -> None:
        try:
            bars = broker.intraday_bars(wider, days=90)  # ~60 Handelstage: 40 Testtage + Vorlauf für den 20-Tage-Schnitt
            base = {**LOOSE, "watchlist": wider, **exit_b}
            # 0.8.5: späte Einstiege und Trades ohne Fortschritt (Befund aus der ersten Live-Woche)
            variants = [
                ("locker 40, Ziel 1,5R + Einstand (aktiv)", base),
                ("keine Käufe in den letzten 90 min", {**base, "no_entry_last_min": 90}),
                ("keine Käufe in den letzten 150 min", {**base, "no_entry_last_min": 150}),
                ("Zeitstop 2 h ohne +0,5R", {**base, "time_stop_min": 120}),
                ("Zeitstop 1 h ohne +0,5R", {**base, "time_stop_min": 60}),
                ("90 min + Zeitstop 2 h", {**base, "no_entry_last_min": 90, "time_stop_min": 120}),
            ]
            for name, over in variants:
                over = dict(over)
                c = config_from_env(over.pop("watchlist", cfg.watchlist), **over)
                r = day_backtest(c, {s: bars.get(s, []) for s in c.watchlist}, test_days=40)
                log.info("DAYTRADER-BACKTEST %s, %d Handelstage: %.2f $ -> %.2f $ (%+.1f%%), %d Trades, %.0f%% Gewinner, "
                         "Schnitt Gewinn %+.2f $ / Verlust %+.2f $", name, r["days"], r["start"], r["end"],
                         (r["end"] / r["start"] - 1) * 100, r["trades"], r["win_rate"] * 100, r["avg_win"], r["avg_loss"])
                log.info("DAYTRADER-AUSSTIEGE %s: %s", name, ", ".join(f"{k} {v}" for k, v in r["exits"].items()))
                if r["stats"]:
                    log.info("DAYTRADER-FILTER %s: %s", name,
                             ", ".join(f"{k} {v}" for k, v in sorted(r["stats"].items(), key=lambda kv: -kv[1])))
        except Exception as e:
            log.warning("Daytrader-Backtest fehlgeschlagen: %s", e)

    # Vergleich im Hintergrund, damit der Daytrader sofort handelt (dauert auf dem Pi einige Minuten)
    threading.Thread(target=compare, name="daytrader-backtest", daemon=True).start()
    storage = Storage(cfg.db_path)
    DayTrader(dcfg, broker, storage, HomeAssistantReporter.from_env(), EarningsCalendar(storage)).run_forever()
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
