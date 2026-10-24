#!/usr/bin/env bash
# Installation auf Raspberry Pi OS / Debian / Ubuntu. Ausführen im Projektordner: bash deploy/install_pi.sh
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get update && sudo apt-get install -y python3-venv
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
[ -f config.yaml ] || cp settings.example.yaml config.yaml
[ -f .env ] || { cp .env.example .env; chmod 600 .env; }
sed -e "s#/home/pi/tradingbot#$PWD#g" -e "s#User=pi#User=$USER#" deploy/tradingbot.service \
  | sudo tee /etc/systemd/system/tradingbot.service >/dev/null
sudo systemctl daemon-reload
echo "Fertig. Trage deine Alpaca-Schlüssel in .env ein, dann:"
echo "  .venv/bin/python -m tradingbot once     # ein Testlauf"
echo "  sudo systemctl enable --now tradingbot  # dauerhaft starten"
echo "  journalctl -u tradingbot -f             # Log ansehen"
