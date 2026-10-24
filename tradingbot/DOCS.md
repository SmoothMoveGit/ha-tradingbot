# Tradingbot

Kauft und verkauft automatisch US-Aktien über Alpaca, mit festem Budget, Risikogrenzen und Nachrichtenanalyse.

> **Risiko:** Automatisierter Handel kann Geld kosten, auch alles. Der Bot startet im Paper-Modus (Spielgeld).
> Echtes Geld erst nach mehreren Wochen Paper-Trading.

## Einrichtung

1. Bei [Alpaca](https://alpaca.markets) registrieren, auf **Paper Trading** wechseln, unter *API Keys* Schlüssel erzeugen.
2. Hier im Tab **Konfiguration** Key ID und Secret eintragen, speichern, Add-on starten.
3. Im Tab **Protokoll** siehst du jeden Handelszyklus (alle 15 Minuten).

## In Home Assistant

Der Bot meldet diese Entitäten (nach jedem Zyklus aktualisiert):

| Entität | Inhalt |
|---|---|
| `sensor.tradingbot_wert` | aktueller Wert (Kapital + offene Positionen) |
| `sensor.tradingbot_kapital` | Startbudget + realisierte Gewinne |
| `sensor.tradingbot_gewinn` | realisierter Gewinn/Verlust |
| `sensor.tradingbot_positionen` | Anzahl offener Positionen (Liste als Attribut) |
| `sensor.tradingbot_status` | handelt / Börse geschlossen / Tageslimit erreicht / Not-Aus |
| `binary_sensor.tradingbot_not_aus` | an, wenn der Not-Aus ausgelöst hat |
| `sensor.tradingbot_vergleich_etf` | Wert von Startbudget und Einzahlungen, hätte man sie in einen MSCI-World-ETF (URTH) gesteckt; Attribut `vorsprung` = Bot minus ETF |

Käufe, Verkäufe und Not-Aus kommen als Benachrichtigung (Option *Benachrichtigungsdienst*, z.B. `notify.mobile_app_dein_handy`).

## Backtest

Beim ersten Start jeder neuen Version testet der Bot seine Regeln gegen die echten Tageskurse der letzten 3 Jahre und schreibt das Ergebnis ins Protokoll (Zeilen mit `BACKTEST`). Nachrichten gibt es rückwirkend nicht, getestet werden Trend-Signal und Risikoregeln.

Ist eine monatliche Einzahlung eingestellt, rechnet der Backtest sie mit ein. Die Rendite bezieht sich dann auf alles Eingezahlte, und der ETF-Vergleich kauft mit denselben Einzahlungen. Zwei Varianten testen einen 2x-Hebel (täglich angepasst wie ein Faktor-Zertifikat, 4 % Kosten pro Jahr). Das ist nur eine Näherung, kein echtes Derivat.

## Strategie

| Strategie | Trend | Stops | Positionen | Reserve | Not-Aus |
|---|---|---|---|---|---|
| standard | 10/30 Tage | 5 % / Trailing 6 %, Gewinnmitnahme 12 % | 4 × 20 % | 10 % | 25 % |
| trendfolger | 50/200 Tage | 15 % / Trailing 15 % | 4 × 20 % | 10 % | 25 % |
| aggressiv | 50/200 Tage | 15 % / Trailing 15 % | 3 × 34 % | 0 % | 50 % |

## Monatliche Einzahlung

Option *Monatliche Einzahlung*: Der Betrag wird am Monatsanfang zum Kapital des Bots addiert. Im Paper-Modus ist das reine Buchhaltung (das Paper-Konto hat genug Spielgeld), im Live-Modus musst du das Geld selbst beim Broker einzahlen.

## Stop-Order bei Alpaca

Für jede Position liegt zusätzlich eine Stop-Order bei Alpaca. Sie gilt bis Handelsschluss und wird jeden Handelstag erneuert. So greift der Stop-Loss auch, wenn der Bot kurz nicht läuft. Ist der Pi über Nacht oder mehrere Tage aus, fehlt der Schutz ab dem nächsten Handelstag.

## Feineinstellungen

Watchlist, Stop-Loss, Positionsgrößen usw. stehen in `config.yaml` im Ordner
`/addon_configs/<id>_tradingbot/` (erreichbar über Samba oder Terminal). Nach Änderungen Add-on neu starten.

## Not-Aus zurücksetzen

Im Terminal-Add-on: `docker exec addon_<id>_tradingbot python -m tradingbot reset-halt -c /config/config.yaml`
