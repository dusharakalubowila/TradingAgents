#!/bin/bash
# Starts MT5 terminal and mt5linux bridge.
# unbuffer (from 'expect' package) provides a real PTY so Wine Python gets
# valid stdin/stdout/stderr handles — fixes: OSError: [WinError 6] Invalid handle
export DISPLAY=:99
export HOME=/root
LOG="/root/.tradingagents/logs"
mkdir -p "$LOG"

# Start MT5 terminal
wine "C:/Program Files/MetaTrader 5/terminal64.exe" /portable >> "$LOG/mt5terminal.log" 2>&1 &
echo "MT5 PID: $!" >> "$LOG/mt5terminal.log"
sleep 20

# Start mt5linux bridge inside a PTY
exec unbuffer wine "C:/Program Files/Python310/python.exe" -m mt5linux >> "$LOG/mt5bridge.log" 2>&1
