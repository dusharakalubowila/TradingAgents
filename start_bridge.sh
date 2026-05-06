#!/bin/bash
# Starts MT5 terminal and mt5linux bridge with proper terminal emulation
export DISPLAY=:99
export HOME=/root
LOG="/root/.tradingagents/logs"
mkdir -p "$LOG"

# Start MT5 terminal
wine "C:/Program Files/MetaTrader 5/terminal64.exe" /portable >> "$LOG/mt5terminal.log" 2>&1 &
echo "MT5 PID: $!" >> "$LOG/mt5terminal.log"
sleep 20

# Use wineconsole to provide proper Windows console handles (fixes stdin issue)
exec wineconsole "C:/Program Files/Python310/python.exe" -m mt5linux
