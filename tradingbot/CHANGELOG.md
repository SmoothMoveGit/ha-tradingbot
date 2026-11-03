# Changelog

## 0.5.0
- Mehr Sensoren für das Home-Assistant-Dashboard „Aktien“: `sensor.tradingbot_unrealisiert` (offener Gewinn), `_bargeld`, `_rendite` (in % aufs Eingezahlte), `_heute` (Tagesänderung), `_drawdown` (Abstand zum Höchststand, mit Not-Aus-Grenze und Stop-Werten), `_marktstimmung` (Nachrichtenlage mit Schlagzeilen und Signalen je Aktie) und `_trades` (Anzahl, letzte 10 Trades).
- `sensor.tradingbot_positionen` hat jetzt das Attribut `details` (Stück, Einstand, Kurs, Wert, Gewinn je Aktie), `sensor.tradingbot_status` zusätzlich Strategie, Watchlist und Zeit des letzten Laufs.

## 0.4.2
- Strategien `trendfolger` und `aggressiv`: Eine einzelne schlechte Schlagzeile löst keinen Notverkauf mehr aus. Verkauft wird nur, wenn die Nachrichtenlage insgesamt schlecht ist (Schnitt ≤ −0,3) oder die Meldung verheerend (≤ −0,85).

## 0.4.1
- Vergleich jetzt mit dem MSCI World (US-ETF URTH) statt dem S&P 500. Neuer Sensor `sensor.tradingbot_vergleich_etf` ersetzt `sensor.tradingbot_vergleich_sp500`; der Vergleich startet neu.

## 0.4.0
- Neue Option *Strategie*: `standard`, `trendfolger` oder `aggressiv` (Werte wie im Backtest getestet). Überschreibt die passenden Einstellungen aus `config.yaml`.

## 0.3.3
- Backtest: aggressive Varianten (Trendfolger mit 3 großen Positionen, ohne Cash-Reserve, Not-Aus erst bei 50 %), auch mit 2x- und 3x-Hebel.
- Not-Aus im Backtest füllt nicht mehr das Protokoll.

## 0.3.2
- Neue Option `monthly_deposit`: monatliche Einzahlung, wird zum Kapital addiert (Gewinne werden weiter mit eingesetzt). Der SPY-Vergleich bekommt dieselben Einzahlungen.
- Backtest rechnet mit den Einzahlungen, Rendite bezogen auf das insgesamt Eingezahlte.
- Backtest-Varianten mit 2x-Hebel (täglich angepasst wie ein Faktor-Zertifikat, 4 % Kosten pro Jahr).

## 0.3.1
- Backtest vergleicht 9 Varianten (Stops, Trendlänge, Handelshäufigkeit, Positionsgröße): Zeitraum A zum Vergleichen, das letzte Jahr B zum Gegenprüfen.

## 0.3.0
- Backtest: Beim ersten Start einer neuen Version werden die Regeln gegen echte Tageskurse der letzten 3 Jahre getestet, Ergebnis im Protokoll.
- Neuer Sensor `sensor.tradingbot_vergleich_sp500`: Was das Startbudget im S&P-500-ETF (SPY) wert wäre, mit Attribut `vorsprung`.
- Stop-Order zusätzlich bei Alpaca hinterlegt (täglich erneuert, zieht beim Trailing-Stop nach). Verkäufe durch diese Order werden erkannt und verbucht.

## 0.2.4
- Protokoll zeigt, ob Claude oder das Lexikon die Nachrichten bewertet.

## 0.2.3
- Klarere Meldung, wenn die Alpaca-Schlüssel fehlen.

## 0.2.2
- Add-on wird in Home Assistant erkannt.

## 0.2.0
- Läuft als Home-Assistant-Add-on, Sensoren und Benachrichtigungen in Home Assistant.

## 0.1.0
- Erster Prototyp: Alpaca Paper Trading, Trend + Nachrichten, Risikogrenzen.
