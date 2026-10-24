# Aktien-Tradingbot

Ein autonomer Bot, der mit einem festen Guthaben Aktien kauft und verkauft, auf Nachrichten reagiert
und auf einem Raspberry Pi oder Mini-PC läuft.

> **Risiko-Hinweis:** Automatisierter Handel kann Geld kosten, auch alles. Dieser Bot ist ein Experiment,
> keine Anlageberatung. Er startet immer im Paper-Modus (Spielgeld). Echtes Geld erst, wenn er
> wochenlang im Paper-Modus sinnvoll gelaufen ist, und nur Geld, dessen Verlust du verkraftest.

## So funktioniert er

Alle 15 Minuten (während die US-Börse offen ist) macht der Bot einen Zyklus:

1. **Nachrichten holen:** Alpaca-News zu den Aktien der Watchlist plus RSS-Feeds (Wirtschaft und Welt).
   Jede Schlagzeile bekommt eine Stimmung von -1 bis +1 (lokales Lexikon oder optional Claude).
   Nachrichten ohne Firmenbezug zählen als „Weltlage".
2. **Signal je Aktie:** 60 % Trend (gleitende Durchschnitte 10/30 Tage + Momentum),
   40 % Nachrichtenstimmung. Eine schlechte Weltlage senkt alle Signale.
3. **Verkaufen**, wenn: Stop-Loss (-5 %), Gewinnmitnahme (+12 %), Trailing-Stop (-6 % vom Hoch),
   sehr negative Nachricht oder Signal kippt.
4. **Kaufen**, wenn das Signal stark genug ist: max. 20 % des Kapitals pro Aktie, max. 4 Positionen,
   10 % bleiben immer als Reserve. Bruchteilsaktien, daher reichen auch kleine Beträge.
5. **Not-Aus:** Ab -3 % am Tag keine Käufe mehr. Ab -25 % vom Höchststand verkauft er alles und stoppt.

**Kapital** = Startbudget + realisierte Gewinne (bzw. minus Verluste). Gewinne werden also wieder eingesetzt.
Der Bot fasst nur Positionen an, die er selbst gekauft hat.

## Schnellstart (Paper-Trading)

1. Kostenloses Konto bei [Alpaca](https://alpaca.markets) anlegen (geht aus Deutschland, für Paper reicht E-Mail).
2. Im Dashboard auf **Paper Trading** wechseln, unter *API Keys* Schlüssel erzeugen.
3. Auf dem Pi:
   ```bash
   cd ~/tradingbot
   bash deploy/install_pi.sh
   nano .env                         # ALPACA_API_KEY und ALPACA_SECRET_KEY eintragen
   .venv/bin/python -m tradingbot once     # ein Zyklus zum Testen
   sudo systemctl enable --now tradingbot  # dauerhaft laufen lassen
   ```
4. Kontrolle: `.venv/bin/python -m tradingbot status` und `journalctl -u tradingbot -f`

Ohne Konto ausprobieren: `python -m tradingbot sim --days 120` (Zufallskurse, offline).

## Konfiguration

Alles steht in `config.yaml` (Vorlage: `settings.example.yaml`): Watchlist, Budget, Risiko-Grenzen,
Gewichtung von Trend und Nachrichten, RSS-Feeds. Schlüssel gehören nur in `.env`.

Bessere Nachrichtenbewertung: `sentiment_engine: claude` und `ANTHROPIC_API_KEY` in `.env`.

## Später mit echtem Geld

- Erst nach mehreren Wochen Paper-Trading mit Ergebnissen, die du verstehst.
- Broker-Optionen aus Deutschland mit API: Alpaca (US-Aktien, Konto in USD, Überweisung ins Ausland)
  oder Interactive Brokers (auch EU-Aktien). Trade Republic hat keine offizielle API.
- In `config.yaml` `mode: live` setzen **und** in `.env` `CONFIRM_LIVE_TRADING=ja-ich-kenne-das-risiko`.
- Steuern: Gewinne bei ausländischen Brokern musst du selbst in der Steuererklärung angeben (Anlage KAP).

## Projektstruktur

```
tradingbot/
  bot.py         Handelszyklus
  strategy.py    Trend- und Kombinationssignal
  news.py        Nachrichten holen, zuordnen, gewichten
  sentiment.py   Stimmungsanalyse (Lexikon / Claude)
  risk.py        Budget, Stops, Not-Aus
  storage.py     SQLite (Trades, Nachrichten, Verlauf)
  broker/        Alpaca, Offline-Simulator, gemeinsame Schnittstelle
deploy/          systemd-Dienst und Installationsskript
tests/           pytest
```
