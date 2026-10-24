# Tradingbot für Home Assistant

Home-Assistant-Add-on-Repository mit einem autonomen Aktien-Tradingbot (Alpaca, Paper Trading zuerst).

> Automatisierter Handel kann zu Verlusten führen. Keine Anlageberatung.

## Installation

1. In Home Assistant: **Einstellungen → Add-ons → Add-on Store → ⋮ (oben rechts) → Repositories**
2. Diese Repository-Adresse eintragen und hinzufügen.
3. Im Store erscheint **Tradingbot** → installieren (der erste Build dauert auf einem Pi 4 einige Minuten).
4. Im Tab **Konfiguration** die Alpaca-Paper-Schlüssel eintragen, dann starten.

Details: [tradingbot/DOCS.md](tradingbot/DOCS.md). Der Bot läuft auch ohne Home Assistant,
siehe [tradingbot/app/README.md](tradingbot/app/README.md).

## Entwicklung

```bash
cd tradingbot/app
pip install -r requirements.txt pytest
python -m pytest
python -m tradingbot sim --days 120
```
