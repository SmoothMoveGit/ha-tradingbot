from datetime import date, datetime, timedelta, timezone

import pytest

from tradingbot.bot import TradingBot
from tradingbot.broker.sim import SimBroker
from tradingbot.config import Config, load_config
from tradingbot.risk import RiskManager
from tradingbot.sentiment import lexicon_score
from tradingbot.storage import Storage


def make_bot(symbols=("AAA",), budget=1000.0):
    cfg = Config(watchlist=list(symbols))
    cfg.news.use_alpaca_news = False
    cfg.risk.start_budget = budget
    broker = SimBroker(budget, list(symbols))
    for s in symbols:  # klarer Aufwärtstrend
        for i in range(40):
            broker.set_price(s, 100 + i)
    return TradingBot(cfg, broker, Storage(":memory:")), broker


def add_news(bot, symbol, headline, hours_ago=0.5):
    item = {"id": headline, "time": datetime.now(timezone.utc) - timedelta(hours=hours_ago), "headline": headline}
    bot.storage.add_news(item, symbol, lexicon_score(headline))


def test_sentiment_direction():
    assert lexicon_score("Apple beats estimates, shares surge") > 0.5
    assert lexicon_score("Bank files for bankruptcy amid fraud probe") < -0.5
    assert lexicon_score("Markets open") == 0


def test_buys_in_uptrend_and_respects_position_size():
    bot, broker = make_bot()
    bot.run_cycle()
    assert "AAA" in broker.holdings
    cost = bot.storage.all_meta()["AAA"]
    assert cost == pytest.approx(1000 * bot.cfg.risk.max_position_pct)


def test_stop_loss_sells():
    bot, broker = make_bot()
    bot.run_cycle()
    broker.set_price("AAA", broker.last_price("AAA") * 0.9)
    bot.run_cycle()
    assert "AAA" not in broker.holdings
    assert bot.storage.realized_pnl() < 0
    assert "Stop-Loss" in bot.storage.recent_trades(1)[0][6]


def test_panic_news_blocks_buy_and_forces_sell():
    bot, broker = make_bot()
    add_news(bot, "AAA", "AAA plunges after fraud investigation and bankruptcy warning")
    bot.run_cycle()
    assert "AAA" not in broker.holdings

    bot2, broker2 = make_bot()
    bot2.run_cycle()
    add_news(bot2, "AAA", "AAA plunges after fraud investigation and bankruptcy warning")
    bot2.run_cycle()
    assert "AAA" not in broker2.holdings


def test_profits_are_reinvested():
    bot, _ = make_bot()
    bot.storage.record_trade("AAA", "sell", 1, 1, "test", pnl=200)
    assert bot.risk.bot_capital() == 1200
    bot.cfg.risk.reinvest_profits = False
    assert bot.risk.bot_capital() == 1000


def test_budget_never_exceeds_cash():
    bot, broker = make_bot(symbols=("A", "B", "C", "D", "E", "F", "G"), budget=1000)
    bot.run_cycle()
    assert broker.cash >= 0
    invested = sum(bot.storage.all_meta().values())
    assert invested <= 1000 * (1 - bot.cfg.risk.min_cash_reserve_pct) + 1e-6
    assert len(broker.holdings) <= bot.cfg.risk.max_positions


def test_daily_loss_and_drawdown_limits():
    cfg = Config()
    risk = RiskManager(cfg, Storage(":memory:"))
    d = date(2026, 1, 5)
    assert risk.check_limits(1000, d) is None
    assert risk.check_limits(960, d) == "day"
    assert risk.check_limits(960, d + timedelta(days=1)) is None
    assert risk.check_limits(700, d + timedelta(days=2)) == "stop"
    assert risk.halted


def test_live_mode_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.delenv("CONFIRM_LIVE_TRADING", raising=False)
    f = tmp_path / "c.yaml"
    f.write_text("mode: live\n")
    with pytest.raises(SystemExit):
        load_config(f)
    monkeypatch.setenv("CONFIRM_LIVE_TRADING", "ja-ich-kenne-das-risiko")
    assert load_config(f).mode == "live"


def test_ignores_positions_not_opened_by_bot():
    bot, broker = make_bot()
    broker.holdings["MANUAL"] = (1.0, 50.0)
    broker.history["MANUAL"] = broker.history["AAA"][:]
    broker.set_price("MANUAL", 1.0)  # -98 %, Bot darf trotzdem nicht verkaufen
    bot.run_cycle()
    assert "MANUAL" in broker.holdings


class FakeReporter:
    def __init__(self):
        self.published, self.notes = [], []

    def publish(self, status):
        self.published.append(status)

    def notify(self, title, message):
        self.notes.append(title)


def test_reports_status_and_trades():
    bot, _ = make_bot()
    bot.reporter = FakeReporter()
    bot.run_cycle()
    s = bot.reporter.published[-1]
    assert s["positions"] == ["AAA"] and s["status"] == "handelt" and not s["halted"]
    assert any("gekauft" in n for n in bot.reporter.notes)


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("TRADINGBOT_MODE", "sim")
    monkeypatch.setenv("TRADINGBOT_START_BUDGET", "250")
    cfg = load_config(None)
    assert cfg.mode == "sim" and cfg.risk.start_budget == 250


def test_homeassistant_reporter_requests(monkeypatch):
    import json
    from tradingbot import homeassistant as ha
    calls = []

    class Resp:
        def close(self):
            pass

    monkeypatch.setattr(ha.urllib.request, "urlopen", lambda req, timeout: calls.append(req) or Resp())
    r = ha.HomeAssistantReporter("http://supervisor/core/api", "tok", "notify.mobile_app_handy")
    r.publish({"value": 301.5, "capital": 300, "realized_pnl": 0, "positions": ["AAPL"], "status": "handelt",
               "mode": "paper", "halted": False})
    r.notify("Titel", "Text")
    urls = [c.full_url for c in calls]
    assert "http://supervisor/core/api/states/sensor.tradingbot_wert" in urls
    assert urls[-1] == "http://supervisor/core/api/services/notify/mobile_app_handy"
    assert json.loads(calls[0].data)["state"] == 301.5
    assert calls[0].headers["Authorization"] == "Bearer tok"


def test_addon_reads_options(tmp_path, monkeypatch):
    import json
    from tradingbot import addon
    opts = tmp_path / "options.json"
    opts.write_text(json.dumps({"alpaca_api_key": "k", "alpaca_secret_key": "s", "mode": "paper",
                                "start_budget": 250, "live_confirmation": "nein"}))
    monkeypatch.setattr(addon, "OPTIONS", opts)
    monkeypatch.setattr(addon, "CONFIG", tmp_path / "cfg" / "config.yaml")
    for k in ("CONFIRM_LIVE_TRADING", "ALPACA_API_KEY", "TRADINGBOT_START_BUDGET"):
        monkeypatch.delenv(k, raising=False)
    calls = []
    import tradingbot.__main__ as cli
    monkeypatch.setattr(cli, "main", lambda argv: calls.append(argv[0]) or 0)
    addon.main()
    addon.main()  # zweiter Start: Backtest nur einmal pro Version
    import os
    assert os.environ["ALPACA_API_KEY"] == "k" and os.environ["TRADINGBOT_START_BUDGET"] == "250"
    assert "CONFIRM_LIVE_TRADING" not in os.environ
    assert (tmp_path / "cfg" / "config.yaml").exists()
    assert calls == ["backtest", "run", "run"]


def test_backtest_on_history():
    import math
    from datetime import datetime, timedelta, timezone
    from tradingbot.backtest import format_result, run_backtest
    from tradingbot.broker.base import Bar
    t0 = datetime(2023, 1, 2, tzinfo=timezone.utc)

    def series(f):
        return [Bar(t0 + timedelta(days=i), f(i), f(i), f(i), f(i), 1e6) for i in range(300)]

    bars = {
        "UP": series(lambda i: 100 * math.exp(0.004 * i)),
        "DOWN": series(lambda i: 100 * math.exp(-0.004 * i)),
        "SPY": series(lambda i: 400 * math.exp(0.001 * i)),
    }
    cfg = Config(watchlist=["UP", "DOWN"])
    cfg.risk.start_budget = 300
    r = run_backtest(cfg, bars)
    assert r["final"] > 300 and r["trades"] >= 1 and r["max_drawdown_pct"] < 0.1
    assert abs(r["benchmark_return_pct"] - (math.exp(0.001 * (299 - 35)) - 1)) < 1e-6
    assert "Vergleich SPY" in format_result(r)[-1]


def test_historical_broker_has_no_lookahead():
    from datetime import date, datetime, timezone
    from tradingbot.backtest import HistoricalBroker
    from tradingbot.broker.base import Bar
    bars = {"A": [Bar(datetime(2024, 1, d, tzinfo=timezone.utc), d, d, d, d, 1) for d in range(1, 11)]}
    b = HistoricalBroker(100, bars)
    b.set_date(date(2024, 1, 5))
    assert b.last_price("A") == 5 and len(b.daily_bars("A", 100)) == 5


def test_benchmark_and_broker_stop():
    bot, broker = make_bot(symbols=("AAA", "SPY"))
    stops = []
    broker.ensure_stop = lambda sym, qty, price: stops.append((sym, round(price, 2)))
    bot.reporter = FakeReporter()
    bot.run_cycle()
    s = bot.reporter.published[-1]
    assert s["benchmark_value"] == pytest.approx(bot.cfg.risk.start_budget)
    assert stops and stops[0][0] in ("AAA", "SPY")
    entry = broker.holdings[stops[0][0]][1]
    assert stops[0][1] == round(entry * (1 - bot.cfg.risk.stop_loss_pct), 2)


def test_sell_by_broker_stop_is_recorded():
    from tradingbot.broker.base import Fill
    bot, broker = make_bot()
    bot.run_cycle()
    qty, _ = broker.holdings.pop("AAA")  # Stop-Order beim Broker hat verkauft
    broker.last_sell_fill = lambda sym, since=None: Fill(sym, "sell", qty, 100.0)
    bot.run_cycle()
    t = bot.storage.recent_trades(5)
    assert any(x[2] == "sell" and "Broker" in x[6] for x in t)
    assert bot.storage.realized_pnl() < 0
