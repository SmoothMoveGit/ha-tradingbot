# Dashboard „Aktien“ – Anleitung

Das Dashboard zeigt alles, was der Tradingbot an Home Assistant meldet: Depotwert, Rendite, Vergleich mit dem MSCI World, Verlauf, Positionen, letzte Trades, Nachrichtenlage, Signale, Risiko und Bot-Status. Design: helle/dunkle Karten mit runden Ecken, Apple-Schrift, Grün/Rot wie in der Aktien-App.

## Voraussetzungen

| Was | Wofür | Wo |
|---|---|---|
| **Mushroom** (HACS) | Kennzahl-Kacheln und Status-Chips | HACS → Suche „Mushroom“ |
| **card-mod** (HACS) | runde Ecken, Schatten, Schrift | HACS → Suche „card-mod“ |
| **Tradingbot ab 0.5.0** | Positionen im Detail, Trades, Nachrichten, Risiko | Einstellungen → Apps → Tradingbot → Aktualisieren |

Mit Tradingbot 0.4.x funktioniert das Dashboard auch schon, zeigt aber bei Positionen, Trades, Nachrichten und Risiko nur einen Hinweis „erscheint nach dem Update auf Version 0.5.0“.

## Variante A: Dashboard ist schon da

Wenn Claude es per Home-Assistant-Zugriff angelegt hat, steht in der linken Seitenleiste **Aktien**. Nichts weiter zu tun.

## Variante B: Von Hand einfügen

1. **Einstellungen → Dashboards → + Dashboard hinzufügen**.
2. **Neues Dashboard von Grund auf** wählen → Weiter.
3. Titel `Aktien`, Symbol `mdi:finance` → **Erstellen**.
4. Das neue Dashboard **Aktien** in der Seitenleiste öffnen.
5. Oben rechts auf den **Stift** (Bearbeiten) tippen.
6. Oben rechts **⋮ (drei Punkte) → Raw-Konfigurationseditor**.
7. Alles im Editor löschen und den kompletten Inhalt von [`aktien.yaml`](aktien.yaml) einfügen.
8. **Speichern** (oben rechts), dann **X** und **Fertig**.
9. Einmal die Seite neu laden (am PC Strg+F5, in der App nach unten ziehen).

## Wenn etwas nicht passt

| Problem | Ursache | Lösung |
|---|---|---|
| Rote Karte „Custom element doesn't exist: mushroom-…“ | Mushroom fehlt | In HACS installieren, Seite neu laden |
| Karten eckig, ohne Schatten | card-mod fehlt oder Browser-Cache | card-mod installieren, Strg+F5 bzw. App: Einstellungen → Frontend-Cache zurücksetzen |
| „Entität nicht verfügbar“ bei Weltlage | Bot noch auf 0.4.x | Add-on auf 0.5.0 aktualisieren und einen Lauf (max. 15 min) abwarten |
| Verlauf leer | Werte kommen erst ab Start | „Langfristig“ füllt sich mit der Zeit (Tageswerte) |

## Erklärung der Zahlen

- **Depotwert**: Bargeld des Bots + aktueller Wert seiner Aktien (nur vom Bot gekaufte).
- **Seit Start**: Depotwert minus alles Eingezahlte (Startbudget + monatliche Einzahlungen).
- **MSCI World**: Was dasselbe Geld im ETF URTH wert wäre, zum Vergleich.
- **Realisiert / Offen**: Gewinn aus verkauften Aktien bzw. Buchgewinn der noch gehaltenen.
- **Weltlage** und **Signale**: −1 = sehr negativ, 0 = neutral, +1 = sehr positiv. Kauf ab Gesamt-Signal über der Kaufschwelle.
- **Abstand zum Höchststand**: wie weit der Depotwert unter seinem bisherigen Hoch liegt. Erreicht er die Not-Aus-Grenze, verkauft der Bot alles und hält an.
