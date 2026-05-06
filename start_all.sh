#!/bin/bash
# Starts MT5 terminal, bridge, and trading bot — all in one command.
# Called automatically by systemd on boot.

BOT_DIR="/home/dushara-kalubowila/Desktop/Trading/TradingAgents"
PYTHON="$BOT_DIR/venv/bin/python"
WINE_PYTHON="/home/dushara-kalubowila/.wine/drive_c/Program Files/Python310/python.exe"
MT5_EXE="/home/dushara-kalubowila/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"
LOG="$HOME/.tradingagents/logs"

mkdir -p "$LOG"

echo "[$(date)] Starting TradingAgents Forex Bot..." | tee -a "$LOG/startup.log"

# Step 1: Start MT5 terminal under Wine
echo "[$(date)] Starting MT5 terminal..." | tee -a "$LOG/startup.log"
DISPLAY=:0 wine "$MT5_EXE" /portable >> "$LOG/mt5terminal.log" 2>&1 &
MT5_PID=$!
echo "[$(date)] MT5 PID: $MT5_PID" | tee -a "$LOG/startup.log"

# Wait for MT5 to start
sleep 15

# Step 2: Start mt5linux bridge
echo "[$(date)] Starting mt5linux bridge..." | tee -a "$LOG/startup.log"
wine "$WINE_PYTHON" -m mt5linux >> "$LOG/mt5bridge.log" 2>&1 &
BRIDGE_PID=$!
echo "[$(date)] Bridge PID: $BRIDGE_PID" | tee -a "$LOG/startup.log"

# Wait for bridge to be ready
sleep 5

# Step 3: Start trading daemon
echo "[$(date)] Starting trading daemon..." | tee -a "$LOG/startup.log"
cd "$BOT_DIR"
"$PYTHON" run_forex_auto.py \
    --mt5-login 415672839 \
    --mt5-password Dkk@20020922 \
    --mt5-server Exness-MT5Trial14 \
    --balance 100.0 \
    --risk-pct 1.0 \
    --max-daily-loss-pct 3.0 \
    >> "$LOG/forex_auto.log" 2>&1 &
BOT_PID=$!
echo "[$(date)] Bot PID: $BOT_PID" | tee -a "$LOG/startup.log"

echo "[$(date)] All services started. Logs at $LOG/" | tee -a "$LOG/startup.log"

# Keep script alive so systemd tracks it
wait $BOT_PID
