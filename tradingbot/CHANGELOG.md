# Changelog

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
