# Changelog

## 0.8.11
- Backtest beim Start vergleicht zusätzlich die Watchlist: aktuelle 10 Werte gegen 25, 35 Aktien und die 40 Werte des Daytraders (gleiche Strategie). Nur Vergleich, der Bot handelt weiter mit seiner Watchlist.

## 0.8.10
- Nachkauf: Sind alle Plätze belegt, füllt der Bot freies Geld (z. B. nach einer Sonderzahlung) auch bei kleinen Lücken in die bestehenden Positionen, statt es liegen zu lassen.

## 0.8.9
- Neue Option „Daytrader Sonderzahlungen gesamt (USD)“: erhöht das Kapital des Daytraders, zählt aber nicht als Gewinn. Die Rendite in sensor.daytrader_wert rechnet ab jetzt gegen Startbudget plus Sonderzahlungen.

## 0.8.8
- SEC-Meldungen sichtbar im Log: Startzeile, wenn die Quelle aktiv ist, und pro Abruf (alle 30 min) „SEC: x Firmen geprüft, y wichtige 8-K-Meldungen“.

## 0.8.7
- Daytrader darf bis zu 5 statt 3 Trades pro Tag machen. Im 40-Tage-Backtest ändert das kaum etwas (+2,5 % bei 78 statt 76 Trades), weil die Grenze selten erreicht wird. Die Vorauswahl nach Tagesmustern aus dem day-trader-skill bleibt aus: zu wenige Trades (14 bzw. 20) und weniger Gewinn (+0,9 % bzw. +1,4 %).

## 0.8.6
- Daytrader kauft nicht mehr in den letzten 150 Minuten vor Börsenschluss (40-Tage-Backtest: +2,5 % bei 76 Trades statt +2,1 % bei 89). Späte Käufe hatten kaum Zeit bis zum Ziel und wurden zum Handelsschluss mit Verlust verkauft. Der Zeitstop hat im Backtest geschadet (−1,4 % bzw. −2,1 %) und bleibt aus.
- Daytrader nutzt die SEC-Meldungen (8-K): Aktie mit wichtiger Meldung am selben Tag wird nicht gekauft, bei schwerer Meldung (Insolvenz, Delisting-Warnung, unzuverlässige Zahlen) 30 Tage nicht. Nutzt die Option sec_user_agent.
- Backtest-Vergleich beim Start: 5 Trades pro Tag, ohne Trade-Grenze und Vorauswahl nach Tagesmustern aus dem day-trader-skill (20-Tage-Hoch, Flagge, Rückkehr über den 20-Tage-Schnitt).

## 0.8.5
- Daytrader: neuer Zeitstop (raus, wenn ein Trade nach X Minuten nicht mindestens +0,5R im Plus ist), zunächst nur im Backtest. Der Varianten-Backtest beim Start vergleicht jetzt späte Einstiege (keine Käufe in den letzten 90 bzw. 150 min) und Zeitstops von 1 h und 2 h mit den aktiven Regeln. Anlass: In der ersten Live-Woche wurden späte Käufe zum Handelsschluss mit Verlust verkauft.

## 0.8.4
- Verkauf wartet, bis Alpaca offene Stop-Orders wirklich storniert hat (bis zu 10 s). Vorher scheiterten Verkäufe manchmal mit "insufficient qty available".

## 0.8.3
- Neue Nachrichtenquelle: SEC-Pflichtmeldungen (8-K). Insolvenz, Delisting-Warnung oder unzuverlässige frühere Zahlen führen zum sofortigen Verkauf und 30 Tagen Kaufsperre; Cyberangriff, Abschreibung und Vorstandswechsel gehen in die Nachrichtenbewertung. Neue Option *SEC-Kontakt* (Name und E-Mail, verlangt die SEC), leer = aus.

## 0.8.2
- Daytrader: Ideen aus dem day-trader-skill (github.com/Jakeschincariol/day-trader-skill) eingebaut, vorerst nur im Backtest. Neu: Opening-Range-Breakout (Spanne der ersten 15 min, Schluss einer 5-min-Kerze darüber, Stop Mitte der Spanne) als eigene Strategie oder zusätzlich zum Pullback, und ein Tagesfilter (nur Aktien über ihrem 20-Tage-Schnitt).
- Varianten-Backtest beim Start vergleicht 6 Varianten auf rund 60 Handelstagen Daten (40 Testtage). Der aktive Handel bleibt unverändert, bis die Zahlen da sind.

## 0.8.1
- Umschichten: Fehlt Bargeld für eine weitere Position, kürzt der Bot zu große Positionen auf ihre Zielgröße (bei *aggressiv* 25 %) und kauft mit dem Erlös die stärkste neue Aktie. So kommt nach dem Wechsel auf 4 Positionen die vierte Aktie dazu, sobald die Börse öffnet und ein Kaufsignal da ist.

## 0.8.0
- Strategie *aggressiv*: 4 Aktien zu je 25 % statt 3 zu je 34 % (breitere Streuung, im Backtest gleiche Rendite). Bestehende Positionen bleiben, die vierte kommt beim nächsten Kauf dazu.

## 0.7.9
- Daytrader handelt jetzt mit dem gelockerten Regelwerk auf 40 Werten (25 Aktien plus 15 weitere große Aktien und Index-ETFs), Kursziel 1,5R statt 2R und Einstand-Stop ab 1R. 40-Tage-Backtest: +2,5 % bei 89 Trades (vorher +1,3 % bei 71 Trades).
- Varianten-Backtest beim Start auf drei Varianten gekürzt.

## 0.7.8
- Daytrader: optionaler Einstand-Stop (Stop wandert auf den Kaufkurs, sobald der Trade 1R im Plus ist, auch bei Alpaca).
- Daytrader schreibt zum Handelsschluss ins Protokoll, an welchen Regeln die Signale des Tages gescheitert sind (DAYTRADER-HEUTE).
- Varianten-Backtest vergleicht jetzt Ausstiege (Ziel 1,5R, Einstand-Stop) und 40 statt 25 Aktien. Gehandelt wird weiter mit „locker, 25 Aktien“.

## 0.7.7
- Varianten-Backtest vergleicht zusätzlich „aggressiv“ mit 4 und 5 Positionen (breitere Streuung). Am Handel ändert sich nichts.

## 0.7.6
- Tagesänderung: Fehlt der gemerkte Schlusswert (Update am Abend), wird der letzte Eintrag im Verlauf genommen.

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
