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

Käufe, Verkäufe und Not-Aus kommen als Benachrichtigung (Option *Benachrichtigungsdienst*, z.B. `notify.mobile_app_dein_handy`).

## Feineinstellungen

Watchlist, Stop-Loss, Positionsgrößen usw. stehen in `config.yaml` im Ordner
`/addon_configs/<id>_tradingbot/` (erreichbar über Samba oder Terminal). Nach Änderungen Add-on neu starten.

## Not-Aus zurücksetzen

Im Terminal-Add-on: `docker exec addon_<id>_tradingbot python -m tradingbot reset-halt -c /config/config.yaml`
