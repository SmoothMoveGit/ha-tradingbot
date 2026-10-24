"""Startpunkt im Home-Assistant-Add-on: liest die Optionen aus der HA-Oberfläche."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

OPTIONS = Path("/data/options.json")
CONFIG = Path("/config/config.yaml")  # im HA-Ordner addon_configs/<slug>_tradingbot/
EXAMPLE = Path(__file__).resolve().parent.parent / "settings.example.yaml"
LIVE_PHRASE = "ja-ich-kenne-das-risiko"


def main() -> int:
    opts = json.loads(OPTIONS.read_text()) if OPTIONS.exists() else {}
    env = {
        "ALPACA_API_KEY": opts.get("alpaca_api_key", ""),
        "ALPACA_SECRET_KEY": opts.get("alpaca_secret_key", ""),
        "ANTHROPIC_API_KEY": opts.get("anthropic_api_key", ""),
        "TRADINGBOT_MODE": opts.get("mode", "paper"),
        "TRADINGBOT_START_BUDGET": str(opts.get("start_budget", 300)),
        "TRADINGBOT_DB_PATH": "/data/tradingbot.db",
        "TRADINGBOT_NOTIFY_SERVICE": opts.get("notify_service", ""),
        "TRADINGBOT_MONTHLY_DEPOSIT": str(opts.get("monthly_deposit", "")),
    }
    if opts.get("anthropic_api_key"):
        env["TRADINGBOT_SENTIMENT"] = "claude"
    if opts.get("live_confirmation", "").strip() == LIVE_PHRASE:
        env["CONFIRM_LIVE_TRADING"] = LIVE_PHRASE
    os.environ.update({k: v for k, v in env.items() if v})

    if not CONFIG.exists():
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(EXAMPLE, CONFIG)
        print(f"Neue Konfiguration angelegt: {CONFIG} (Watchlist und Risiko dort anpassbar)", flush=True)

    from .__main__ import main as cli
    marker = OPTIONS.parent / f"backtest-{os.getenv('TRADINGBOT_VERSION', 'dev')}.done"
    if env["TRADINGBOT_MODE"] != "sim" and not marker.exists():
        try:  # einmal pro Version: Regeln gegen echte Kurse prüfen, Ergebnis steht im Protokoll
            cli(["backtest", "--variants", "-c", str(CONFIG)])
            marker.touch()
        except Exception as e:
            print(f"Backtest fehlgeschlagen: {e}", flush=True)
    return cli(["run", "-c", str(CONFIG)])


if __name__ == "__main__":
    raise SystemExit(main())
