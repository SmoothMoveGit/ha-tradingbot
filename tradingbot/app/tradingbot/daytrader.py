"""Zweiter Bot zum Vergleich: Daytrading (nur Spielgeld, eigenes Alpaca-Konto).

Standard ist Michis Regelwerk "Trend-Pullback" auf 15-Minuten-Kerzen (VWAP, EMA 9/21, RSI 14, ATR 14,
Volumen, Bestätigungskerze, Chance-Risiko 2:1, Risiko 0,5 % je Trade). Die frühere einfache
Ausbruch-Variante bleibt für den Vergleich im Backtest erhalten. Nur Long, keine Leerverkäufe.
Eigene Datenbank, eigene Sensoren (sensor.daytrader_*).
"""
from __future__ import annotations

import json
import logging
import os
import time
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .broker.base import Account, Bar, Fill, Position
from .homeassistant import Reporter
from .storage import Storage

log = logging.getLogger("tradingbot.daytrader")
QUIET = logging.getLogger("tradingbot.daytrader.backtest")
QUIET.setLevel(logging.WARNING)
NY = ZoneInfo("America/New_York")


@dataclass
class DayConfig:
    watchlist: list
    start_budget: float = 1100.0
    extra_deposit: float = 0.0          # Sonderzahlungen gesamt (USD): mehr Kapital, aber kein Gewinn
    strategy: str = "pullback"          # pullback (Regelwerk 15 min) | orb | combo (pullback + orb) | breakout (alt)
    # Pullback-Regelwerk
    bar_minutes: int = 15
    risk_per_trade_pct: float = 0.005   # 0,5 % des Kapitals je Trade
    reward_risk: float = 2.0            # Kursziel = 2R
    atr_stop_buffer: float = 0.2        # Stop 0,2 x ATR unter dem Pullback-Tief
    max_chase_atr: float = 0.5          # Einstieg verwerfen, wenn Kurs schon so weit über dem Auslöser ist
    min_risk_pct: float = 0.002         # Stop-Abstand unter 0,2 % lohnt sich nach Kosten nicht
    max_trades_per_day: int = 3
    max_losses_in_row: int = 2
    max_position_pct: float = 0.34
    rsi_min: float = 50.0
    rsi_max: float = 70.0
    min_ema_gap: float = 0.0005         # EMA 9 mindestens so weit über EMA 21 (Anteil vom Kurs)
    max_vwap_crosses: int = 4           # ab so vielen VWAP-Kreuzungen in 8 Kerzen = Seitwärtsmarkt
    pullback_tol: float = 0.001         # Tief muss bis auf diesen Abstand an die EMA 9 kommen
    vol_factor: float = 1.0             # Volumen der Signalkerze > Faktor x Schnitt der letzten 20
    resistance_filter: bool = True
    entry_valid_bars: int = 1           # so viele Kerzen bleibt der Einstieg gültig
    breakeven_r: float = 0.0            # >0: Stop auf Einstand, sobald der Kurs so viele R im Plus ist
    time_stop_min: int = 0              # >0: nach so vielen Minuten raus, wenn der Trade nicht mind. time_stop_r im Plus ist
    time_stop_r: float = 0.5
    daily_setup: str = ""               # Vorauswahl nach Tageskerzen (Skill-Scanner): breakout20 | flag | any
    trend_ma: int = 0                   # >0: nur Aktien, deren Vortagesschluss über dem N-Tage-Schnitt liegt
    # Opening-Range-Breakout (aus dem day-trader-skill): Spanne der ersten 15 min, Schluss einer
    # 5-min-Kerze darüber = Einstieg, Stop Mitte der Spanne, Ziel reward_risk x Risiko
    orb_minutes: int = 15
    orb_stop: str = "mid"               # mid | low
    orb_vol_factor: float = 0.0         # >0: Ausbruchskerze braucht so viel x Volumen der Spannen-Kerzen
    # Ausbruch-Variante
    take_profit_pct: float = 0.015
    stop_loss_pct: float = 0.010
    breakout_bars: int = 6
    min_momentum: float = 0.003
    # gemeinsam
    max_positions: int = 3
    daily_loss_limit_pct: float = 0.01
    no_entry_first_min: int = 15
    no_entry_last_min: int = 45
    flat_before_close_min: int = 15
    interval_minutes: int = 2
    min_order_value: float = 10.0
    earnings_guard_days: int = 1


# Zusätzliche, sehr liquide US-Werte: mehr Kandidaten heißt mehr Signale, ohne die Regeln aufzuweichen
EXTRA_SYMBOLS = ["AMD", "AVGO", "TSLA", "NFLX", "ORCL", "CRM", "COST", "WMT", "XOM", "UNH",
                 "MA", "HD", "PG", "LLY", "BAC"]

# Noch mehr Kandidaten (große, liquide Werte und Index-ETFs)
MORE_SYMBOLS = ["QQQ", "SPY", "IWM", "SMH", "XLF", "PLTR", "UBER", "MU", "QCOM", "ADBE",
                "INTC", "PYPL", "PEP", "CSCO", "DIS"]

# Grundliste des Daytraders (bis 0.8.10 aus der Hauptbot-Watchlist übernommen; jetzt fest, damit eine
# Änderung der Hauptbot-Watchlist den Daytrader nicht mitverändert)
DAY_BASE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "V", "KO", "JNJ"]

# Nur für den Vergleich (0.8.11): weitere große, liquide US-Werte, 20 Stück -> 60 Werte
TEST_SYMBOLS_60 = ["GS", "MS", "WFC", "C", "CVX", "ABBV", "MRK", "PFE", "TXN", "AMAT",
                   "LRCX", "IBM", "NOW", "SHOP", "COIN", "MRVL", "ARM", "ANET", "PANW", "CAT"]

# Nur für den Vergleich (0.8.11): noch einmal 40 Stück -> 100 Werte
TEST_SYMBOLS_100 = ["BA", "GE", "HON", "LMT", "NKE", "SBUX", "MCD", "T", "VZ", "CMCSA",
                    "TMO", "ABT", "AMGN", "GILD", "BMY", "UPS", "DE", "RTX", "SCHW", "AXP",
                    "BLK", "SNOW", "CRWD", "NET", "DDOG", "ABNB", "DASH", "SOFI", "RIVN", "F",
                    "GM", "SLB", "COP", "OXY", "XLE", "XLK", "DIA", "KRE", "XLV", "SMCI"]

# Gelockerte Fassung des Regelwerks (Michi hat Anpassungen freigegeben, 2026-11-03)
LOOSE = {"rsi_min": 45.0, "rsi_max": 75.0, "min_ema_gap": 0.0002, "max_vwap_crosses": 6,
         "pullback_tol": 0.003, "vol_factor": 0.8, "entry_valid_bars": 2}

BREAKOUT = {"strategy": "breakout", "bar_minutes": 5, "max_positions": 5, "max_position_pct": 0.20,
            "daily_loss_limit_pct": 0.03, "max_trades_per_day": 99, "max_losses_in_row": 99}


# Indikatoren
def ema(values: list[float], n: int) -> list[float]:
    k, out = 2 / (n + 1), []
    for v in values:
        out.append(v if not out else out[-1] + k * (v - out[-1]))
    return out


def rsi(closes: list[float], n: int = 14) -> float:
    if len(closes) <= n:
        return 50.0
    gains = losses = 0.0
    for a, b in zip(closes[:n], closes[1:n + 1]):
        gains += max(b - a, 0)
        losses += max(a - b, 0)
    g, l = gains / n, losses / n
    for a, b in zip(closes[n:], closes[n + 1:]):
        g = (g * (n - 1) + max(b - a, 0)) / n
        l = (l * (n - 1) + max(a - b, 0)) / n
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


def atr(bars: list[Bar], n: int = 14) -> float:
    trs = [max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close)) for p, b in zip(bars, bars[1:])]
    if not trs:
        return 0.0
    a = sum(trs[:n]) / min(n, len(trs))
    for t in trs[n:]:
        a = (a * (n - 1) + t) / n
    return a


def vwap(bars: list[Bar]) -> float:
    vol = sum(b.volume for b in bars)
    if not vol:
        return sum(b.close for b in bars) / len(bars)
    return sum((b.high + b.low + b.close) / 3 * b.volume for b in bars) / vol


def session_of(b: Bar) -> date:
    return b.time.astimezone(NY).date()


def aggregate(bars: list[Bar], minutes: int, now: datetime) -> list[Bar]:
    """5-Minuten-Kerzen zu fertigen 15-Minuten-Kerzen (ab 9:30 New York) zusammenfassen."""
    if minutes == 5:
        return bars
    groups: dict[datetime, list[Bar]] = {}
    for b in bars:
        t = b.time.astimezone(NY)
        since_open = (t.hour * 60 + t.minute) - (9 * 60 + 30)
        if since_open < 0:
            continue
        start = t.replace(second=0, microsecond=0) - timedelta(minutes=since_open % minutes)
        groups.setdefault(start, []).append(b)
    out = []
    for start, bs in sorted(groups.items()):
        if start + timedelta(minutes=minutes) > now:
            continue  # Kerze noch nicht abgeschlossen
        out.append(Bar(start, bs[0].open, max(b.high for b in bs), min(b.low for b in bs), bs[-1].close,
                       sum(b.volume for b in bs)))
    return out


def bullish_confirmation(c: Bar, prev: Bar) -> bool:
    rng = c.high - c.low
    if rng <= 0:
        return False
    body = abs(c.close - c.open)
    strong_green = c.close > c.open and (c.close - c.low) / rng >= 0.7
    engulfing = prev.close < prev.open and c.close > c.open and c.open <= prev.close and c.close >= prev.open
    hammer = (min(c.open, c.close) - c.low) >= 2 * max(body, rng * 0.05) and (c.close - c.low) / rng >= 0.66
    return strong_green or engulfing or hammer


def pullback_setup(bars: list[Bar], cfg: DayConfig, stats: dict | None = None) -> dict | None:
    """Long-Setup Trend-Pullback (Regelwerk Abschnitt 2 und 6). bars: fertige Kerzen, mehrere Tage.
    stats zählt, an welcher Regel ein Setup scheitert (für die Auswertung im Backtest)."""
    def no(reason: str):
        if stats is not None:
            stats[reason] = stats.get(reason, 0) + 1
        return None
    if len(bars) < 30:
        return None
    today = session_of(bars[-1])
    session = [b for b in bars if session_of(b) == today]
    if len(session) < 2:
        return None
    closes = [b.close for b in bars]
    e9, e21 = ema(closes, 9), ema(closes, 21)
    c, prev = bars[-1], bars[-2]
    v = vwap(session)
    a = atr(bars[-30:])
    r = rsi(closes[-60:])
    if c.close <= v:
        return no("unter VWAP")
    if not (e9[-1] > e21[-1] and e9[-1] > e9[-2] and e21[-1] > e21[-2]):
        return no("kein EMA-Aufwärtstrend")
    if not cfg.rsi_min <= r <= cfg.rsi_max:
        return no("RSI außerhalb")
    # Seitwärtsmarkt: Kurs kreuzt VWAP ständig oder EMAs liegen ineinander
    crosses = sum(1 for x, y in zip(session[-8:], session[-7:]) if (x.close - v) * (y.close - v) < 0)
    if crosses >= cfg.max_vwap_crosses or (e9[-1] - e21[-1]) / c.close < cfg.min_ema_gap:
        return no("Seitwärtsmarkt")
    # Rücklauf zur EMA 9/21 in den letzten Kerzen, ohne Schluss unter EMA 21
    recent = range(len(bars) - 4, len(bars))
    if not any(bars[i].low <= e9[i] * (1 + cfg.pullback_tol) for i in recent):
        return no("kein Rücklauf zur EMA 9")
    if any(bars[i].close < e21[i] for i in recent):
        return no("Schluss unter EMA 21")
    if not bullish_confirmation(c, prev):
        return no("keine Bestätigungskerze")
    vols = [b.volume for b in bars[-21:-1]]
    if vols and c.volume <= cfg.vol_factor * sum(vols) / len(vols):
        return no("zu wenig Volumen")
    trigger = c.high * 1.0005
    stop = min(b.low for b in bars[-4:]) - cfg.atr_stop_buffer * a
    risk = trigger - stop
    if risk <= 0 or risk / trigger < cfg.min_risk_pct:
        return no("Stop zu eng")
    target = trigger + cfg.reward_risk * risk
    # markanter Widerstand direkt darüber (Tageshoch oder Vortageshoch zwischen Einstieg und 1R)
    highs = [max(b.high for b in session[:-1])] if len(session) > 1 else []
    prev_day = [b for b in bars if session_of(b) < today]
    if prev_day:
        last = session_of(prev_day[-1])
        highs.append(max(b.high for b in prev_day if session_of(b) == last))
    if cfg.resistance_filter and any(trigger < h < trigger + risk for h in highs):
        return no("Widerstand darüber")
    if stats is not None:
        stats["Signal"] = stats.get("Signal", 0) + 1
    return {"trigger": trigger, "stop": stop, "target": target, "atr": a, "expires": c.time + (1 + cfg.entry_valid_bars) * (c.time - prev.time),
            "why": f"Pullback RSI {r:.0f}, Vol {c.volume / (sum(vols) / len(vols)):.1f}x" if vols else "Pullback"}


def daily_setup_ok(closes: list[float], kind: str) -> bool:
    """Tagesmuster aus dem Skill-Scanner (nur Schlusskurse, abgeschlossene Tage):
    breakout20 = letzter Schluss über allen 20 davor; flag = +10 % in 10 Tagen, dann 5 Tage in 5 %-Spanne;
    any = eins davon oder Rückkehr über den 20-Tage-Schnitt."""
    if len(closes) < 21:
        return True  # ohne Daten nicht sperren
    last = closes[-1]
    breakout = last > max(closes[-21:-1])
    flag = len(closes) >= 15 and closes[-6] / closes[-16 if len(closes) >= 16 else 0] - 1 > 0.10 and \
        max(closes[-5:]) / min(closes[-5:]) - 1 <= 0.05
    ma_prev, ma_now = sum(closes[-21:-1]) / 20, sum(closes[-20:]) / 20
    reclaim = closes[-2] < ma_prev and last > ma_now
    if kind == "breakout20":
        return breakout
    if kind == "flag":
        return flag
    return breakout or flag or reclaim


def orb_setup(bars5: list[Bar], cfg: DayConfig, now: datetime, stats: dict | None = None) -> dict | None:
    """Opening-Range-Breakout auf 5-Minuten-Kerzen (Regel aus dem day-trader-skill, trader-entry/-exit):
    Spanne = erste orb_minutes, Auslöser = erste fertige Kerze danach, die ÜBER dem Spannenhoch schließt.
    Nur der erste Ausbruch des Tages zählt; nur wenn er gerade erst passiert ist (letzte fertige Kerze)."""
    now = now.astimezone(NY)
    done = [b for b in bars5 if session_of(b) == now.date() and b.time + timedelta(minutes=5) <= now]
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    rng = [b for b in done if b.time < open_t + timedelta(minutes=cfg.orb_minutes)]
    after = [b for b in done if b.time >= open_t + timedelta(minutes=cfg.orb_minutes)]
    if len(rng) < cfg.orb_minutes // 5 or not after:
        return None
    hi, lo = max(b.high for b in rng), min(b.low for b in rng)
    first = next((b for b in after if b.close > hi), None)
    if first is None or first is not after[-1]:
        return None  # noch kein Ausbruch, oder er ist schon älter (nur der erste, frische zählt)
    def no(reason: str):
        if stats is not None:
            stats[reason] = stats.get(reason, 0) + 1
        return None
    if cfg.orb_vol_factor > 0 and first.volume < cfg.orb_vol_factor * sum(b.volume for b in rng) / len(rng):
        return no("ORB zu wenig Volumen")
    trigger = first.close
    stop = (hi + lo) / 2 if cfg.orb_stop == "mid" else lo
    risk = trigger - stop
    if risk <= 0 or risk / trigger < cfg.min_risk_pct:
        return no("ORB Stop zu eng")
    if stats is not None:
        stats["ORB-Signal"] = stats.get("ORB-Signal", 0) + 1
    return {"trigger": trigger, "stop": stop, "target": trigger + cfg.reward_risk * risk,
            "atr": atr(done[-15:]) if len(done) > 1 else 0.0, "expires": first.time + timedelta(minutes=15),
            "why": f"ORB über {hi:.2f}"}


def breakout_setup(bars: list[Bar], cfg: DayConfig) -> dict | None:
    """Alte Variante: Ausbruch über das 30-Minuten-Hoch, über VWAP, sofort kaufen."""
    today = session_of(bars[-1]) if bars else None
    session = [b for b in bars if session_of(b) == today]
    n = cfg.breakout_bars
    if len(session) < n + 1:
        return None
    last = session[-1].close
    momentum = last / session[-n - 1].close - 1
    if last > max(b.high for b in session[-n - 1:-1]) and last > vwap(session) and momentum >= cfg.min_momentum:
        return {"trigger": last, "stop": last * (1 - cfg.stop_loss_pct), "target": last * (1 + cfg.take_profit_pct),
                "atr": 0.0, "expires": session[-1].time + timedelta(minutes=10), "why": f"Ausbruch {momentum:+.1%}"}
    return None


class DayTrader:
    def __init__(self, cfg: DayConfig, broker, storage: Storage, reporter: Reporter | None = None, earnings=None,
                 sec=None):
        self.sec = sec  # SEC-8-K-Meldungen (live): betroffene Aktie an diesem Tag nicht kaufen
        self._sec_today: dict[str, str] = {}
        self.cfg = cfg
        self.broker = broker
        self.storage = storage
        self.reporter = reporter or Reporter()
        self.earnings = earnings
        self.status = "gestartet"
        self.pending: dict[str, dict] = {}
        self.log = log
        self.stats: dict | None = None  # im Backtest: Gründe, warum kein Setup entstand
        self._seen: dict[str, datetime] = {}
        self.live_stats: dict = {}  # live: warum heute kein Setup entstand, Ausgabe zum Tagesende
        self._trend: dict[tuple[str, date], bool] = {}

    def _trend_ok(self, sym: str, today: date) -> bool:
        """Vortagesschluss über dem trend_ma-Tage-Schnitt (Tagesfilter wie im Skill-Scanner)."""
        key = (sym, today)
        if key not in self._trend:
            n = self.cfg.trend_ma
            try:
                closes = [b.close for b in self.broker.daily_bars(sym, n + 5) if session_of(b) < today][-n:]
            except Exception:
                closes = []
            self._trend[key] = len(closes) < n or closes[-1] > sum(closes) / n  # ohne Daten nicht sperren
        return self._trend[key]

    def _daily_ok(self, sym: str, today: date) -> bool:
        key = (sym + ":setup", today)
        if key not in self._trend:
            try:
                closes = [b.close for b in self.broker.daily_bars(sym, 30) if session_of(b) < today]
            except Exception:
                closes = []
            self._trend[key] = daily_setup_ok(closes, self.cfg.daily_setup)
        return self._trend[key]

    def _check_sec(self, now: datetime) -> None:
        """Wichtige 8-K-Meldungen von heute: Aktie heute nicht kaufen; schwere Meldung = 30 Tage Sperre."""
        from . import sec as secmod
        today = now.date()
        if self._sec_today.get("_day") != str(today):
            self._sec_today = {"_day": str(today)}
        try:
            start = datetime(today.year, today.month, today.day, tzinfo=NY)
            for f in self.sec.fetch(self.cfg.watchlist, start, now):
                sym = f["symbols"][0]
                if sym not in self._sec_today:
                    self.log.info("DAYTRADER-SEC %s: %s, heute kein Kauf", sym, f["label"])
                self._sec_today[sym] = f["label"]
                if f.get("hard"):
                    secmod.block(self.storage, sym, f["label"], today)
        except Exception as e:
            self.log.warning("SEC-Abfrage fehlgeschlagen: %s", e)
        for sym in self.cfg.watchlist:
            if sym not in self._sec_today and (label := secmod.blocked(self.storage, sym, today)):
                self._sec_today[sym] = label

    def capital(self) -> float:
        return self.cfg.start_budget + self.cfg.extra_deposit + self.storage.realized_pnl()

    def _day(self, today: date) -> dict:
        return json.loads(self.storage.get(f"day:{today}", '{"entries": 0, "losses_in_row": 0, "pnl": 0.0}'))

    def _save_day(self, today: date, d: dict) -> None:
        self.storage.set(f"day:{today}", json.dumps(d))

    def _plan(self, sym: str) -> dict:
        return json.loads(self.storage.get(f"plan:{sym}", "{}"))

    def _record_exit(self, sym: str, fill: Fill, reason: str, meta: dict, now: datetime) -> None:
        pnl = fill.qty * fill.price - meta.get(sym, 0.0)
        self.storage.record_trade(sym, "sell", fill.qty, fill.price, reason, pnl, when=now)
        self.storage.close_meta(sym)
        meta.pop(sym, None)
        today = now.astimezone(NY).date()
        d = self._day(today)
        d["pnl"] += pnl
        d["losses_in_row"] = d["losses_in_row"] + 1 if pnl < 0 else 0
        self._save_day(today, d)
        self.log.info("VERKAUF %s %.4f @ %.2f | %s | G/V %+.2f", sym, fill.qty, fill.price, reason, pnl)

    def _sell(self, sym: str, reason: str, meta: dict, now: datetime) -> None:
        fill = self.broker.sell_all(sym)
        if fill:
            self._record_exit(sym, fill, reason, meta, now)

    def cycle(self, now: datetime | None = None) -> None:
        now = (now or datetime.now(timezone.utc)).astimezone(NY)
        today = now.date()
        c = self.cfg
        if not self.broker.market_open():
            self.status = "Börse geschlossen"
            self.pending.clear()
            return
        held = self.broker.positions()
        meta = dict(self.storage.all_meta())
        for sym in list(meta):  # beim Broker per Stop verkauft
            if sym not in held:
                fill = self.broker.last_sell_fill(sym, datetime.fromisoformat(self.storage.get_meta(sym)[2]))
                if fill:
                    self._record_exit(sym, fill, "Stop beim Broker", meta, now)
                else:
                    self.storage.close_meta(sym)
                    meta.pop(sym)
        mins_left = self.broker.minutes_to_close(now)
        if mins_left <= c.flat_before_close_min:
            if self.live_stats:
                self.log.info("DAYTRADER-HEUTE %s: %s", today, ", ".join(
                    f"{k} {v}" for k, v in sorted(self.live_stats.items(), key=lambda kv: -kv[1])))
                self.live_stats = {}
            for sym in list(meta):
                self._sell(sym, "Handelsschluss", meta, now)
            self.pending.clear()
            self.status = "Tagesende, alles verkauft"
            return

        # Ausstieg: Stop oder Kursziel
        for sym in list(meta):
            pos, plan = held.get(sym), self._plan(sym)
            if not pos or not plan:
                continue
            if pos.current_price <= plan["stop"]:
                self._sell(sym, ("Einstand-Stop" if plan.get("be") else "Stop-Loss") + f" {pos.pnl_pct:+.1%}", meta, now)
            elif pos.current_price >= plan["target"]:
                self._sell(sym, f"Kursziel {pos.pnl_pct:+.1%}", meta, now)
            elif c.time_stop_min and "t" in plan and now - datetime.fromisoformat(plan["t"]) >= timedelta(minutes=c.time_stop_min) \
                    and pos.current_price < plan["entry"] + c.time_stop_r * plan["risk"]:
                self._sell(sym, f"Zeitstop {pos.pnl_pct:+.1%}", meta, now)  # kein Fortschritt: Platz und Risiko freigeben
            elif c.breakeven_r > 0 and not plan.get("be") and "entry" in plan and \
                    pos.current_price >= plan["entry"] + c.breakeven_r * (plan["entry"] - plan["stop"]):
                plan.update(stop=plan["entry"], be=True)  # ab jetzt kein Verlust mehr möglich (bis auf Spanne)
                self.storage.set(f"plan:{sym}", json.dumps(plan))
                self.broker.ensure_stop(sym, pos.qty, plan["stop"])

        d = self._day(today)
        unrealized = sum(held[s].market_value - meta[s] for s in meta if s in held)
        if d["pnl"] + unrealized <= -c.daily_loss_limit_pct * self.capital():
            self.status = "Tagesverlustgrenze erreicht"
            return
        if d["losses_in_row"] >= c.max_losses_in_row:
            self.status = f"Pause nach {d['losses_in_row']} Verlusttrades"
            return
        if d["entries"] >= c.max_trades_per_day:
            self.status = "Tageslimit Trades erreicht"
            return
        open_min = (now - now.replace(hour=9, minute=30, second=0, microsecond=0)).total_seconds() / 60
        if open_min < c.no_entry_first_min or mins_left <= c.no_entry_last_min:
            self.status = "handelt (keine neuen Käufe)"
            return
        self.status = "handelt"

        raw = self.broker.intraday_bars(c.watchlist, now, days=0 if c.strategy in ("breakout", "orb") else 6)
        soon = {}
        if self.earnings and c.strategy != "breakout":
            soon = self.earnings.upcoming(c.watchlist, today, c.earnings_guard_days)
        if self.sec:
            self._check_sec(now)
            soon = {**soon, **{k: v for k, v in self._sec_today.items() if k != "_day"}}
        for sym in c.watchlist:
            bars5 = raw.get(sym, [])
            if not bars5 or sym in meta or sym in soon:
                continue
            counter = self.stats if self.stats is not None else self.live_stats
            if c.trend_ma and c.strategy != "breakout" and not self._trend_ok(sym, today):
                if self._seen.get(sym + ":trend") != today:
                    counter["unter Tages-Schnitt"] = counter.get("unter Tages-Schnitt", 0) + 1
                    self._seen[sym + ":trend"] = today
                continue
            if c.daily_setup and c.strategy != "breakout" and not self._daily_ok(sym, today):
                if self._seen.get(sym + ":setup") != today:
                    counter["kein Tagesmuster"] = counter.get("kein Tagesmuster", 0) + 1
                    self._seen[sym + ":setup"] = today
                continue
            bars = aggregate(bars5, c.bar_minutes, now)
            plan = None
            if c.strategy == "breakout":
                plan = breakout_setup(bars, c)
            if c.strategy in ("pullback", "combo"):
                new_bar = bool(bars) and self._seen.get(sym) != bars[-1].time  # jede Kerze nur einmal zählen
                plan = pullback_setup(bars, c, counter if new_bar else None)
                if bars:
                    self._seen[sym] = bars[-1].time
            if not plan and c.strategy in ("orb", "combo"):
                last5 = bars5[-1].time if bars5 else None
                new5 = self._seen.get(sym + ":5") != last5
                plan = orb_setup(bars5, c, now, counter if new5 else None)
                self._seen[sym + ":5"] = last5
            if plan and (sym not in self.pending or self.pending[sym]["trigger"] != plan["trigger"]):
                self.pending[sym] = plan

        cash = self.broker.account().cash
        for sym, plan in sorted(self.pending.items(), key=lambda kv: kv[1]["trigger"]):
            if now >= plan["expires"] or sym in meta:
                self.pending.pop(sym, None)
                continue
            price = raw.get(sym, [None])[-1].close if raw.get(sym) else None
            if price is None or price < plan["trigger"]:
                continue
            self.pending.pop(sym, None)
            if price > plan["trigger"] + c.max_chase_atr * plan["atr"] or price <= plan["stop"]:
                continue  # Kurs weggelaufen: nicht hinterherkaufen
            if len(meta) >= c.max_positions or d["entries"] >= c.max_trades_per_day:
                break
            risk_share = price - plan["stop"]
            if c.strategy == "breakout":
                amount = self.capital() * c.max_position_pct
            else:
                amount = self.capital() * c.risk_per_trade_pct / risk_share * price
            amount = min(amount, self.capital() * c.max_position_pct, self.capital() - sum(meta.values()), cash)
            if amount < c.min_order_value:
                continue
            fill = self.broker.buy_notional(sym, amount)
            if not fill:
                continue
            cost = fill.qty * fill.price
            cash -= cost
            self.storage.open_meta(sym, cost, fill.price, when=now)
            meta[sym] = cost
            self.storage.set(f"plan:{sym}", json.dumps({"stop": plan["stop"], "target": plan["target"],
                                                        "entry": fill.price, "t": now.isoformat(),
                                                        "risk": max(fill.price - plan["stop"], 1e-9)}))
            d["entries"] += 1
            self._save_day(today, d)
            reason = f"{plan['why']}, Stop {plan['stop']:.2f}, Ziel {plan['target']:.2f}"
            self.storage.record_trade(sym, "buy", fill.qty, fill.price, reason, when=now)
            self.broker.ensure_stop(sym, fill.qty, plan["stop"])
            self.log.info("KAUF %s %.4f @ %.2f (%.2f) | %s", sym, fill.qty, fill.price, cost, reason)

    def publish(self) -> None:
        try:
            held = self.broker.positions()
            meta = self.storage.all_meta()
            value = self.capital() - sum(meta.values()) + sum(held[s].market_value for s in meta if s in held)
            trades = [
                {"zeit": t, "symbol": sym, "art": "Kauf" if side == "buy" else "Verkauf", "preis": round(price, 2),
                 "gewinn": round(pnl or 0.0, 2), "grund": reason}
                for t, sym, side, qty, price, pnl, reason in self.storage.recent_trades(10)
            ]
            self.reporter.publish_daytrader({
                "value": value, "capital": self.capital(), "start_budget": self.cfg.start_budget + self.cfg.extra_deposit,
                "deposits": self.cfg.extra_deposit,
                "realized_pnl": self.storage.realized_pnl(), "positions": sorted(meta),
                "status": self.status, "trade_count": self.storage.trade_count(), "trades": trades,
            })
        except Exception:
            self.log.exception("Daytrader-Status konnte nicht gemeldet werden")

    def run_forever(self) -> None:
        self.log.info("Daytrader gestartet (%s), Startbudget %.2f $ + Sonderzahlungen %.2f $, Kapital %.2f $, Intervall %d min",
                 self.cfg.strategy, self.cfg.start_budget, self.cfg.extra_deposit, self.capital(), self.cfg.interval_minutes)
        while True:
            try:
                self.cycle()
            except Exception:
                self.log.exception("Fehler im Daytrader-Zyklus")
            self.publish()
            time.sleep(self.cfg.interval_minutes * 60)


class IntradaySim:
    """Spielt historische 5-Minuten-Kerzen ab (für den Backtest). Ausführung zum Schlusskurs der Kerze."""

    def __init__(self, bars: dict[str, list[Bar]], cash: float, slippage: float = 0.0005):
        self.bars = bars
        self.cash = cash
        self.slippage = slippage  # halbe Spanne zwischen Kauf- und Verkaufskurs
        self.holdings: dict[str, tuple[float, float]] = {}
        self.now = None
        self.idx = {s: 0 for s in bars}
        self._times = {s: [b.time for b in bs] for s, bs in bars.items()}

    def set_time(self, now: datetime) -> None:
        self.now = now
        for s, bs in self.bars.items():
            i = self.idx[s]
            while i < len(bs) and bs[i].time + timedelta(minutes=5) <= now:
                i += 1
            self.idx[s] = i

    def _price(self, sym: str) -> float:
        return self.bars[sym][self.idx[sym] - 1].close

    def market_open(self) -> bool:
        return True

    def minutes_to_close(self, now: datetime) -> float:
        n = now.astimezone(NY)
        return (n.replace(hour=16, minute=0, second=0, microsecond=0) - n).total_seconds() / 60

    def intraday_bars(self, symbols, now, days: int = 0) -> dict[str, list[Bar]]:
        d = now.astimezone(NY).date() - timedelta(days=days)
        first = datetime(d.year, d.month, d.day, tzinfo=NY)
        out = {}
        for s in symbols:
            bs = self.bars.get(s, [])
            out[s] = bs[bisect_left(self._times[s], first) if s in self._times else 0: self.idx.get(s, 0)]
        return out

    def positions(self) -> dict[str, Position]:
        return {s: Position(s, q, p, self._price(s)) for s, (q, p) in self.holdings.items()}

    def account(self) -> Account:
        eq = self.cash + sum(p.market_value for p in self.positions().values())
        return Account(self.cash, eq, self.cash)

    def buy_notional(self, sym: str, amount: float) -> Fill | None:
        if not self.idx.get(sym):
            return None
        price = self._price(sym) * (1 + self.slippage)
        qty = amount / price
        self.cash -= amount
        self.holdings[sym] = (qty, price)
        return Fill(sym, "buy", qty, price)

    def sell_all(self, sym: str) -> Fill | None:
        if sym not in self.holdings:
            return None
        qty, _ = self.holdings.pop(sym)
        price = self._price(sym) * (1 - self.slippage)
        self.cash += qty * price
        return Fill(sym, "sell", qty, price)

    def ensure_stop(self, *a) -> None:
        pass

    def daily_bars(self, sym: str, days: int) -> list[Bar]:
        """Tageskerzen aus den 5-Minuten-Kerzen (nur abgeschlossene Tage vor der Simulationszeit)."""
        if not hasattr(self, "_daily"):
            self._daily = {}
        if sym not in self._daily:
            byday: dict[date, list[Bar]] = {}
            for b in self.bars.get(sym, []):
                byday.setdefault(session_of(b), []).append(b)
            self._daily[sym] = [Bar(datetime(d.year, d.month, d.day, 16, tzinfo=NY), bs[0].open, max(x.high for x in bs),
                                    min(x.low for x in bs), bs[-1].close, sum(x.volume for x in bs))
                                for d, bs in sorted(byday.items())]
        today = self.now.astimezone(NY).date()
        return [b for b in self._daily[sym] if session_of(b) < today][-days:]

    def last_sell_fill(self, *a):
        return None


def backtest(cfg: DayConfig, bars: dict[str, list[Bar]], test_days: int | None = None) -> dict:
    """Regeln über historische 5-Minuten-Kerzen, alle 5 min ein Zyklus. Die ersten Tage dienen nur
    zum Einlaufen der Indikatoren, wenn test_days gesetzt ist."""
    from dataclasses import replace
    cfg = replace(cfg, extra_deposit=0.0)  # Backtest immer mit dem Startbudget
    sim = IntradaySim(bars, cfg.start_budget)
    bot = DayTrader(cfg, sim, Storage(":memory:"))
    bot.stats = {}
    bot.log = QUIET  # Backtest-Trades nicht ins Protokoll, sonst sehen sie echt aus
    times = sorted({b.time + timedelta(minutes=5) for bs in bars.values() for b in bs
                    if (9, 30) <= (b.time.astimezone(NY).hour, b.time.astimezone(NY).minute) < (16, 0)})
    all_days = sorted({t.astimezone(NY).date() for t in times})
    if test_days:
        start = all_days[-test_days] if len(all_days) >= test_days else all_days[0]
        times = [t for t in times if t.astimezone(NY).date() >= start]
    days = set()
    for t in times:
        days.add(t.astimezone(NY).date())
        sim.set_time(t)
        bot.cycle(t)
    rows = bot.storage.db.execute("SELECT pnl, reason FROM trades WHERE side='sell'").fetchall()
    sells = [p for p, _ in rows]
    exits: dict[str, int] = {}
    for _, reason in rows:
        key = (reason or "?").split(" ")[0]
        exits[key] = exits.get(key, 0) + 1
    wins = [p for p in sells if p > 0]
    losses = [p for p in sells if p <= 0]
    return {"start": cfg.start_budget, "end": bot.capital(), "days": len(days), "trades": len(sells),
            "win_rate": len(wins) / len(sells) if sells else 0.0,
            "avg_win": sum(wins) / len(wins) if wins else 0.0,
            "avg_loss": sum(losses) / len(losses) if losses else 0.0, "stats": bot.stats, "exits": exits}


def config_from_env(watchlist: list, **overrides) -> DayConfig:
    cfg = DayConfig(watchlist=watchlist, start_budget=float(os.getenv("DAYTRADER_BUDGET") or 1100),
                    extra_deposit=float(os.getenv("DAYTRADER_EXTRA_DEPOSIT") or 0))
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg
