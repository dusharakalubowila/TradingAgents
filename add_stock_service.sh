#!/bin/bash
# Run on VPS to add the stock trading service alongside the existing forex bot
set -e

BOT_DIR="/root/TradingAgents"
VENV="$BOT_DIR/venv"
LOG="/root/.tradingagents/logs"

echo "[1/3] Writing forex-stocks.service..."
cat > ~/.config/systemd/user/forex-stocks.service << EOF
[Unit]
Description=Stock CFD Auto-Trading Daemon
After=forex-mt5.service
Requires=forex-mt5.service

[Service]
Type=simple
WorkingDirectory=$BOT_DIR
ExecStartPre=/bin/sleep 35
ExecStart=$VENV/bin/python $BOT_DIR/run_stock_auto.py \
    --mt5-login 415672839 \
    --mt5-password Dkk@20020922 \
    --mt5-server Exness-MT5Trial14 \
    --balance 100.0 \
    --risk-pct 2.0 \
    --max-daily-loss-pct 5.0
Restart=always
RestartSec=30
StandardOutput=append:$LOG/stock_auto.log
StandardError=append:$LOG/stock_auto.log

[Install]
WantedBy=default.target
EOF

echo "[2/3] Enabling and starting service..."
systemctl --user daemon-reload
systemctl --user enable forex-stocks.service
systemctl --user start forex-stocks.service
sleep 5

echo "[3/3] Status:"
systemctl --user status forex-stocks.service --no-pager -l

echo ""
echo "Stock daemon running. Logs: tail -f $LOG/stock_auto.log"
echo "Trades fire at: 14:30, 17:00, 20:30 UTC (Mon-Fri)"
