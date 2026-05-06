#!/bin/bash
# Installs the forex bot as a systemd service that auto-starts on VPS reboot.
# Run once: bash setup_daemon.sh

set -e

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$INSTALL_DIR/venv"
PYTHON="$VENV/bin/python"
SCRIPT="$INSTALL_DIR/run_forex_auto.py"
SERVICE_NAME="forex-bot"
USER="$(whoami)"
LOG_DIR="$HOME/.tradingagents/logs"

mkdir -p "$LOG_DIR"

echo "=== TradingAgents Forex Bot — Daemon Installer ==="
echo "Install dir : $INSTALL_DIR"
echo "Python      : $PYTHON"
echo "User        : $USER"
echo ""

# ── Read MT5 credentials ──────────────────────────────────────────────────────
MT5_LOGIN="${MT5_LOGIN:-415672839}"
MT5_PASSWORD="${MT5_PASSWORD:-Dkk@20020922}"
MT5_SERVER="${MT5_SERVER:-Exness-MT5Trial14}"

# ── Write systemd service file ────────────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=TradingAgents Forex Bot Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON $SCRIPT \\
    --mt5-login $MT5_LOGIN \\
    --mt5-password $MT5_PASSWORD \\
    --mt5-server $MT5_SERVER \\
    --balance 100.0 \\
    --risk-pct 1.0 \\
    --max-daily-loss-pct 3.0

Restart=always
RestartSec=30
StandardOutput=append:$LOG_DIR/forex_auto.log
StandardError=append:$LOG_DIR/forex_auto.log
Environment="PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=multi-user.target
EOF

echo "Service file written: $SERVICE_FILE"

# ── Enable and start ──────────────────────────────────────────────────────────
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start  "$SERVICE_NAME"

echo ""
echo "=== Done! Forex bot is running as a system service ==="
echo ""
echo "Useful commands:"
echo "  Check status : sudo systemctl status $SERVICE_NAME"
echo "  View logs    : tail -f $LOG_DIR/forex_auto.log"
echo "  Stop bot     : sudo systemctl stop $SERVICE_NAME"
echo "  Start bot    : sudo systemctl start $SERVICE_NAME"
echo "  Restart bot  : sudo systemctl restart $SERVICE_NAME"
echo "  Remove bot   : sudo systemctl disable $SERVICE_NAME"
