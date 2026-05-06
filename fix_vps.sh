#!/bin/bash
# Run on VPS to fix two issues:
#   1. numpy must be pinned to 1.24.4 AFTER MetaTrader5 install (MT5 deps can upgrade it)
#   2. Install `expect` so unbuffer can provide a PTY to Wine Python (fixes WinError 6)
set -e
export DISPLAY=:99
export HOME=/root
LOG="/root/.tradingagents/logs"
WINE_PY="C:/Program Files/Python310/python.exe"

echo "[1/4] Stopping forex-mt5 service..."
systemctl --user stop forex-mt5.service 2>/dev/null || true

echo "[2/4] Force-reinstalling numpy==1.24.4 inside Wine Python..."
wine "$WINE_PY" -m pip install "numpy==1.24.4" --force-reinstall -q
echo "Verifying numpy version:"
wine "$WINE_PY" -c "import numpy; print('numpy', numpy.__version__)"

echo "[3/4] Installing expect (provides unbuffer for PTY)..."
apt-get install -y expect -q

echo "[4/4] Restarting services..."
systemctl --user start forex-mt5.service
sleep 25
echo "--- mt5bridge.log (last 20 lines) ---"
tail -20 "$LOG/mt5bridge.log" 2>/dev/null || echo "(no log yet)"
echo ""
systemctl --user status forex-mt5.service --no-pager -l
