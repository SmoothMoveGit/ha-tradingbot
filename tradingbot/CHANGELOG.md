# Changelog

## 0.7.5
- Hauptbot, Sensor *heute*: Bezug ist jetzt der Schlusswert des letzten Handelstags statt des Werts beim ersten Lauf des Tages (Kurssprünge über Nacht fehlten). Gilt auch für das Tagesverlust-Limit. Einzahlungen zählen nicht als Tagesgewinn.

## 0.7.4
- Daytrader handelt jetzt mit dem gelockerten Regelwerk auf 25 statt 10 Aktien (RSI 45–75, EMA-Abstand 0,02 %, bis 5 VWAP-Kreuzungen, Rücklauf bis 0,3 % an die EMA 9, Volumen über 80 % des Schnitts, Einstieg 2 Kerzen gültig). Im 40-Tage-Backtest: +1,0 % bei 72 Trades, Original-Regelwerk −0,5 % bei 12 Trades.
- Varianten-Backtest beim Start auf fünf Varianten gekürzt.

## 0.7.3
- Varianten-Backtest: Fehler bei den Varianten mit 25 Aktien behoben, zusätzlich wird gezählt, wie Trades enden (Kursziel, Stop, Handelsschluss).

## 0.7.2
- Daytrader: Filter des Regelwerks sind jetzt einstellbar (RSI-Bereich, EMA-Abstand, VWAP-Kreuzungen, Abstand zur EMA 9, Volumen, Widerstand, Gültigkeit des Einstiegs). Gehandelt wird weiter mit dem unveränderten Regelwerk.
- Beim Start vergleicht ein Backtest über 40 Handelstage sieben Varianten (u. a. gelockert, 5-Minuten-Kerzen, 25 statt 10 Aktien) und zählt, an welcher Regel Signale scheitern. Läuft im Hintergrund, der Daytrader handelt sofort.

## 0.7.1
- Nachkauf funktioniert bei Alpaca: der offene Stop wird vor dem Kauf entfernt und danach neu gesetzt (Alpaca lehnte sonst als „wash trade“ ab).
- Quartalszahlen-Kalender: browserähnliche Anfrage an Nasdaq, nach einem Fehler erst nach einer Stunde neuer Versuch.

## 0.7.0
- Daytrader handelt nach dem Regelwerk „Trend-Pullback“ (15-Minuten-Kerzen): Kurs über VWAP, EMA 9 über EMA 21 und beide steigend, RSI 50–70, Rücklauf zur EMA, bullische Bestätigungskerze mit überdurchschnittlichem Volumen. Einstieg über dem Hoch der Bestätigungskerze, Stop 0,2 ATR unter dem Pullback-Tief, Ziel 2R, Risiko 0,5 % je Trade. Höchstens 3 Trades am Tag, Pause nach 2 Verlusten in Folge, Tagesverlustgrenze 1 %. Keine Trades im Seitwärtsmarkt, vor Quartalszahlen oder unter einem nahen Widerstand. Nur Long.
- Beim Start Backtest über 20 Handelstage: Regelwerk und alte Ausbruch-Variante im Vergleich.

## 0.6.1
- Daytrader-Backtest schreibt seine simulierten Käufe und Verkäufe nicht mehr ins Protokoll.

## 0.6.0
- Zweiter Bot zum Vergleich: Daytrader (nur Spielgeld, eigenes Alpaca-Paper-Konto). Kauft Ausbrüche auf 5-Minuten-Kursen, bis zu 5 Aktien, verkauft bei +1,5 % oder -1 % und ist zum Handelsschluss immer komplett draußen. Beim Start Backtest über die letzten 30 Tage. Sensoren `sensor.daytrader_*`.

## 0.5.4
- Nachkauf: Liegt eine gehaltene Aktie nach Einzahlungen um mindestens ein Viertel unter ihrer Zielgröße und ist das Signal weiter positiv, kauft der Bot nach. Vorher blieb neues Geld liegen, solange alle Plätze belegt waren. Gilt auch im Backtest.
- Stop-Order bei Alpaca wird auch bei geänderter Stückzahl erneuert.

## 0.5.3
- Neue Option *Sonderzahlungen gesamt*: Einmalzahlungen erhöhen das Kapital des Bots, der ETF-Vergleich kauft mit demselben Betrag am selben Tag nach.

## 0.5.2
- Claude-Bewertung robuster: Ergebnisse werden über die Nummer der Meldung zugeordnet, kleinere Pakete (20 statt 40). Fehlt eine einzelne Bewertung, wird nur diese Meldung einfach bewertet statt das ganze Paket.

## 0.5.1
- Doppelte Meldungen (gleiche Überschrift aus mehreren Quellen) und allgemeine Meldungen ohne Wirtschaftsbezug (z.B. Sport) gehen nicht mehr an Claude. Spart Kosten und macht die Bewertung sauberer.

## 0.5.0
- Claude bewertet jede Nachricht für alle Aktien der Watchlist, auch indirekt: Probleme bei Zulieferern, Kunden oder Konkurrenten wirken auf die eigene Aktie (meist schwächer).
- Nachrichten von Partnerfirmen werden mitgeholt (z.B. TSMC für Apple und Nvidia). Liste unter `related` in `config.yaml`, sonst eingebaute Standardliste.
- Bis zu 500 statt 50 Alpaca-Meldungen pro Abruf.
- Keine neuen Käufe in den 2 Tagen vor Quartalszahlen (Termine aus dem öffentlichen Nasdaq-Kalender; ist er nicht erreichbar, läuft der Bot normal weiter).
- Claude denkt bei der Bewertung nur kurz nach (geringere Kosten).

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
