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
| `sensor.tradingbot_unrealisiert` | offener (noch nicht realisierter) Gewinn/Verlust der Positionen |
| `sensor.tradingbot_bargeld` | freies Geld des Bots; Attribut `investiert` |
| `sensor.tradingbot_rendite` | Rendite in % bezogen auf Startbudget + Einzahlungen |
| `sensor.tradingbot_heute` | Wertänderung seit Handelsbeginn heute in % |
| `sensor.tradingbot_drawdown` | Abstand zum bisherigen Höchststand in %; Attribute mit Not-Aus-Grenze und Stop-Werten |
| `sensor.tradingbot_marktstimmung` | Nachrichtenlage −1 bis +1; Attribute `aktien`, `signale`, `schlagzeilen` |
| `sensor.tradingbot_trades` | Anzahl Trades; Attribut `letzte` (die letzten 10) |

Das fertige Dashboard „Aktien“ liegt in [`dashboard/aktien.yaml`](../dashboard/aktien.yaml).

Käufe, Verkäufe und Not-Aus kommen als Benachrichtigung (Option *Benachrichtigungsdienst*, z.B. `notify.mobile_app_dein_handy`).

## Backtest

Beim ersten Start jeder neuen Version testet der Bot seine Regeln gegen die echten Tageskurse der letzten 3 Jahre und schreibt das Ergebnis ins Protokoll (Zeilen mit `BACKTEST`). Nachrichten gibt es rückwirkend nicht, getestet werden Trend-Signal und Risikoregeln.

Ist eine monatliche Einzahlung eingestellt, rechnet der Backtest sie mit ein. Die Rendite bezieht sich dann auf alles Eingezahlte, und der ETF-Vergleich kauft mit denselben Einzahlungen. Zwei Varianten testen einen 2x-Hebel (täglich angepasst wie ein Faktor-Zertifikat, 4 % Kosten pro Jahr). Das ist nur eine Näherung, kein echtes Derivat.

## Nachrichten

Alle 15 Minuten holt der Bot die Meldungen der letzten 24 Stunden: Alpaca-Nachrichten zu den Aktien der Watchlist und ihren Partnerfirmen (`related`) sowie die RSS-Feeds. Mit Anthropic-Schlüssel bewertet Claude jede Meldung für jede betroffene Aktie, auch indirekt über Zulieferer, Kunden und Konkurrenten, und zusätzlich für den Gesamtmarkt. Ohne Schlüssel zählt eine Meldung über eine Partnerfirma halb.

Vor Quartalszahlen (Standard: 2 Tage) kauft der Bot die betroffene Aktie nicht neu.

## SEC-Pflichtmeldungen (8-K)

Trägst du unter **SEC-Kontakt** deinen Namen und deine E-Mail ein (z. B. `Max Muster max@example.com`), liest der Bot alle 30 Minuten die Pflichtmeldungen der US-Börsenaufsicht zu den Aktien der Watchlist. Die SEC verlangt diese Angabe, sie wird nur an die SEC geschickt.

- **Insolvenz (1.03), Delisting-Warnung (3.01) oder frühere Zahlen unzuverlässig (4.02):** Der Bot verkauft die Aktie sofort und kauft sie 30 Tage lang nicht.
- **Cyberangriff (1.05), Abschreibung (2.06), Wechsel im Vorstand (5.02):** Die Meldung wird wie eine normale Nachricht bewertet.

Idee nach trader-news aus github.com/Jakeschincariol/day-trader-skill (MIT-Lizenz).

## Strategie

| Strategie | Trend | Stops | Positionen | Reserve | Not-Aus |
|---|---|---|---|---|---|
| standard | 10/30 Tage | 5 % / Trailing 6 %, Gewinnmitnahme 12 % | 4 × 20 % | 10 % | 25 % |
| trendfolger | 50/200 Tage | 15 % / Trailing 15 % | 4 × 20 % | 10 % | 25 % |
| aggressiv | 50/200 Tage | 15 % / Trailing 15 % | 4 × 25 % | 0 % | 50 % |
| momentum | 12-Monats-Rendite (ohne letzten Monat) | keine | 4 × 25 % | 0 % | 50 % |

**momentum:** Am ersten Handelstag jedes Monats nimmt der Bot die 4 Aktien der Watchlist mit der besten Rendite der letzten 12 Monate (ohne den letzten Monat), verkauft, was herausfällt, und kürzt zu große Positionen auf ein Viertel. Neues Geld (Einzahlungen) geht sofort in die 4 Aktien. Es gibt keine Stops; verkauft wird außerhalb der Rotation nur bei schweren SEC-Meldungen, sehr schlechten Nachrichten und beim Not-Aus. Im Protokoll steht jeden Monat eine Zeile `ROTATION JJJJ-MM`.

## Monatliche Einzahlung

Option *Monatliche Einzahlung*: Der Betrag wird am Monatsanfang zum Kapital des Bots addiert. Im Paper-Modus ist das reine Buchhaltung (das Paper-Konto hat genug Spielgeld), im Live-Modus musst du das Geld selbst beim Broker einzahlen.

## Sonderzahlung

Option *Sonderzahlungen gesamt*: Summe aller Einmalzahlungen. Erhöhst du den Wert (z.B. von 0 auf 735), bucht der Bot die Differenz einmal zum Kapital. Der ETF-Vergleich kauft mit diesem Betrag am selben Tag nach, damit der Vergleich fair bleibt. Den Wert später nicht wieder senken, Auszahlungen werden nicht gebucht.

## Nachkauf

Sind alle Positionsplätze belegt, wird neues Geld (monatlich oder Sonderzahlung) in die gehaltenen Aktien gesteckt: Liegt eine Position mindestens 25 % unter ihrer Zielgröße und ist ihr Signal weiter positiv, kauft der Bot bis zur Zielgröße nach. Vor Quartalszahlen und nach sehr schlechten Nachrichten nicht.

## Daytrader (Vergleich)

Trägst du die Schlüssel eines zweiten Alpaca-Paper-Kontos ein, läuft zusätzlich ein Daytrading-Bot. Er handelt nur mit Spielgeld, auch wenn der Hauptbot auf live steht. Regelwerk „Trend-Pullback“ auf 15-Minuten-Kerzen, nur Long:

- Kurs über der Session-VWAP, EMA 9 über EMA 21 und beide steigend, RSI(14) zwischen 50 und 70.
- Rücklauf zur EMA 9/21 in den letzten Kerzen, ohne Schluss unter der EMA 21.
- Bullische Bestätigungskerze (kräftig grün, Hammer oder Engulfing) mit mehr Volumen als der Schnitt der letzten 20 Kerzen.
- Einstieg, sobald der Kurs das Hoch der Bestätigungskerze übersteigt (innerhalb der nächsten Kerze, nicht hinterherkaufen). Stop 0,2 × ATR unter dem Pullback-Tief, Kursziel 2 × Risiko.
- Positionsgröße: 0,5 % Risiko des Kapitals je Trade, höchstens ein Drittel des Kapitals je Aktie.
- Höchstens 3 Trades am Tag, nach 2 Verlusten in Folge Pause, Tagesverlustgrenze 1 %, 15 Minuten vor Schluss wird alles verkauft.
- Kein Trade im Seitwärtsmarkt (VWAP ständig gekreuzt, EMAs ineinander), am Tag vor Quartalszahlen, bei zu kleinem Stop-Abstand (unter 0,2 %) oder wenn das Tageshoch bzw. Vortageshoch direkt darüber liegt.

Beim Start rechnet er einen Backtest über die letzten 20 Handelstage und vergleicht mit der alten Ausbruch-Variante.

Hinweis: Echtes Daytrading ist in den USA bei Konten unter 25.000 $ auf 3 Tagestrades in 5 Tagen begrenzt. Das Paper-Konto hat 100.000 $ Spielgeld, deshalb greift die Regel im Test nicht.

## Stop-Order bei Alpaca

Für jede Position liegt zusätzlich eine Stop-Order bei Alpaca. Sie gilt bis Handelsschluss und wird jeden Handelstag erneuert. So greift der Stop-Loss auch, wenn der Bot kurz nicht läuft. Ist der Pi über Nacht oder mehrere Tage aus, fehlt der Schutz ab dem nächsten Handelstag.

## Feineinstellungen

Watchlist, Stop-Loss, Positionsgrößen usw. stehen in `config.yaml` im Ordner
`/addon_configs/<id>_tradingbot/` (erreichbar über Samba oder Terminal). Nach Änderungen Add-on neu starten.

## Not-Aus zurücksetzen

Im Terminal-Add-on: `docker exec addon_<id>_tradingbot python -m tradingbot reset-halt -c /config/config.yaml`
