#!/bin/bash
# Run this on VPS to finish the setup
# Usage: bash finish_setup.sh

set -e
export DISPLAY=:99
LOG="/root/.tradingagents/logs"
mkdir -p "$LOG"
mkdir -p ~/.config/systemd/user

echo "[1/4] Writing systemd services..."

cat > ~/.config/systemd/user/forex-xvfb.service << 'EOF'
[Unit]
Description=Virtual Display for Wine
After=default.target
[Service]
Type=simple
ExecStart=/usr/bin/Xvfb :99 -screen 0 1024x768x16 -ac
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
EOF

cat > ~/.config/systemd/user/forex-mt5.service << 'EOF'
[Unit]
Description=MT5 Terminal + mt5linux Bridge
After=forex-xvfb.service
Requires=forex-xvfb.service
[Service]
Type=simple
Environment="DISPLAY=:99"
Environment="HOME=/root"
ExecStart=/bin/bash -c 'wine "C:/Program Files/MetaTrader 5/terminal64.exe" /portable >> /root/.tradingagents/logs/mt5terminal.log 2>&1 & sleep 20 && wine "C:/Program Files/Python310/python.exe" -m mt5linux >> /root/.tradingagents/logs/mt5bridge.log 2>&1'
Restart=always
RestartSec=20
[Install]
WantedBy=default.target
EOF

cat > ~/.config/systemd/user/forex-bot.service << 'EOF'
[Unit]
Description=Forex Trading Daemon
After=forex-mt5.service
Requires=forex-mt5.service
[Service]
Type=simple
WorkingDirectory=/root/TradingAgents
ExecStartPre=/bin/sleep 30
ExecStart=/root/TradingAgents/venv/bin/python /root/TradingAgents/run_forex_auto.py \
    --mt5-login 415672839 \
    --mt5-password Dkk@20020922 \
    --mt5-server Exness-MT5Trial14 \
    --balance 100.0 \
    --risk-pct 1.0 \
    --max-daily-loss-pct 3.0
Restart=always
RestartSec=30
StandardOutput=append:/root/.tradingagents/logs/forex_auto.log
StandardError=append:/root/.tradingagents/logs/forex_auto.log
[Install]
WantedBy=default.target
EOF

echo "[2/4] Enabling services..."
loginctl enable-linger root
systemctl --user daemon-reload
systemctl --user enable forex-xvfb.service forex-mt5.service forex-bot.service

echo "[3/4] Starting services..."
systemctl --user start forex-xvfb.service
sleep 5
systemctl --user start forex-mt5.service
sleep 30
systemctl --user start forex-bot.service
sleep 5

echo "[4/4] Status check..."
systemctl --user status forex-xvfb.service --no-pager -l
systemctl --user status forex-mt5.service  --no-pager -l
systemctl --user status forex-bot.service  --no-pager -l

echo ""
echo "============================================================"
echo " DONE! Bot is running. Check logs:"
echo " tail -f /root/.tradingagents/logs/forex_auto.log"
echo "============================================================"
