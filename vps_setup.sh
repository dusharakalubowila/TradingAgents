#!/bin/bash
# ============================================================
# TradingAgents VPS Full Automation Setup
# Run ONCE on your Linux VPS after cloning the repo.
# After this, everything starts automatically on boot.
# ============================================================
# What this does:
#   1. Installs all dependencies (Wine, Xvfb, Python)
#   2. Installs MT5 and Python inside Wine
#   3. Creates 3 systemd services:
#      - forex-xvfb    : Virtual display (Wine needs this on VPS)
#      - forex-mt5     : MT5 terminal + mt5linux bridge
#      - forex-bot     : Trading daemon (runs 24/7)
#   4. Everything auto-starts on VPS reboot
# ============================================================

set -e

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$BOT_DIR/venv"
WINE_PY="C:/Program Files/Python310/python.exe"
MT5_EXE="C:/Program Files/MetaTrader 5/terminal64.exe"
LOG_DIR="$HOME/.tradingagents/logs"
USER="$(whoami)"
HOME_DIR="$HOME"

mkdir -p "$LOG_DIR"

echo "============================================================"
echo " TradingAgents VPS Setup"
echo " Install dir: $BOT_DIR"
echo " User: $USER"
echo "============================================================"

# ── Step 1: System packages ───────────────────────────────────
echo ""
echo "[1/6] Installing system packages..."
sudo dpkg --add-architecture i386
sudo apt update -q
sudo apt install -y \
    wine64 wine32 winetricks wget \
    xvfb x11vnc \
    python3 python3-pip python3-venv \
    git curl

# ── Step 2: Python venv ───────────────────────────────────────
echo ""
echo "[2/6] Setting up Python virtual environment..."
cd "$BOT_DIR"
python3 -m venv venv
"$VENV/bin/pip" install -e "." --index-url https://pypi.org/simple/ -q
"$VENV/bin/pip" install ta smartmoneyconcepts python-dotenv mt5linux \
    --index-url https://pypi.org/simple/ -q
echo "Python venv ready."

# ── Step 3: Wine Python + MT5 ─────────────────────────────────
echo ""
echo "[3/6] Installing Windows Python and MT5 under Wine..."

# Set Wine display to virtual
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x16 &
XVFB_PID=$!
sleep 3

# Install Windows Python silently
if [ ! -f "$HOME/.wine/drive_c/Program Files/Python310/python.exe" ]; then
    echo "Downloading Windows Python 3.10..."
    wget -q https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe -O /tmp/python310.exe
    wine /tmp/python310.exe /quiet InstallAllUsers=1 PrependPath=1
    sleep 10
    echo "Windows Python installed."
fi

# Install MetaTrader5 + mt5linux in Wine Python
wine "$WINE_PY" -m pip install "numpy==1.24.4" MetaTrader5 mt5linux -q
echo "Wine Python packages installed."

# Install MT5 terminal silently
if [ ! -f "$HOME/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe" ]; then
    echo "Downloading MT5..."
    wget -q "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" -O /tmp/mt5setup.exe
    wine /tmp/mt5setup.exe /auto
    sleep 30
    echo "MT5 installed."
fi

kill $XVFB_PID 2>/dev/null

# ── Step 4: Create .env ───────────────────────────────────────
echo ""
echo "[4/6] Writing .env config..."
if [ ! -f "$BOT_DIR/.env" ]; then
cat > "$BOT_DIR/.env" << 'ENVEOF'
DEEPSEEK_API_KEY=sk-84f465546ce140ab8c5e6f9b8f35f8e7

MT5_LOGIN=415672839
MT5_PASSWORD=Dkk@20020922
MT5_SERVER=Exness-MT5Trial14
ENVEOF
echo ".env created."
fi

# ── Step 5: Create systemd services ──────────────────────────
echo ""
echo "[5/6] Installing systemd services..."

mkdir -p "$HOME_DIR/.config/systemd/user"

# Service 1: Virtual display (Xvfb) ─────────────────────────
cat > "$HOME_DIR/.config/systemd/user/forex-xvfb.service" << EOF
[Unit]
Description=Virtual Display for Forex Bot (Wine needs this)
After=default.target

[Service]
Type=simple
ExecStart=/usr/bin/Xvfb :99 -screen 0 1024x768x16 -ac
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

# Service 2: MT5 terminal + bridge ───────────────────────────
cat > "$HOME_DIR/.config/systemd/user/forex-mt5.service" << EOF
[Unit]
Description=MT5 Terminal + mt5linux Bridge
After=forex-xvfb.service network-online.target
Requires=forex-xvfb.service

[Service]
Type=forking
Environment="DISPLAY=:99"
Environment="HOME=$HOME_DIR"
ExecStartPre=/bin/sleep 5
ExecStart=$BOT_DIR/start_mt5_bridge.sh
Restart=always
RestartSec=15

[Install]
WantedBy=default.target
EOF

# Service 3: Trading daemon ───────────────────────────────────
cat > "$HOME_DIR/.config/systemd/user/forex-bot.service" << EOF
[Unit]
Description=TradingAgents Forex Trading Daemon
After=forex-mt5.service
Requires=forex-mt5.service

[Service]
Type=simple
WorkingDirectory=$BOT_DIR
ExecStartPre=/bin/sleep 20
ExecStart=$VENV/bin/python $BOT_DIR/run_forex_auto.py \
    --mt5-login 415672839 \
    --mt5-password Dkk@20020922 \
    --mt5-server Exness-MT5Trial14 \
    --balance 100.0 \
    --risk-pct 1.0 \
    --max-daily-loss-pct 3.0
Restart=always
RestartSec=30
StandardOutput=append:$LOG_DIR/forex_auto.log
StandardError=append:$LOG_DIR/forex_auto.log

[Install]
WantedBy=default.target
EOF

# ── Step 6: MT5 bridge startup script ────────────────────────
cat > "$BOT_DIR/start_mt5_bridge.sh" << EOF
#!/bin/bash
export DISPLAY=:99
export HOME=$HOME_DIR
LOG="$LOG_DIR"
mkdir -p "\$LOG"

# Start MT5 terminal
wine "$MT5_EXE" /portable >> "\$LOG/mt5terminal.log" 2>&1 &
echo \$! > /tmp/mt5terminal.pid
sleep 20

# Start mt5linux bridge
wine "$WINE_PY" -m mt5linux >> "\$LOG/mt5bridge.log" 2>&1 &
echo \$! > /tmp/mt5bridge.pid

echo "MT5 and bridge started."
EOF
chmod +x "$BOT_DIR/start_mt5_bridge.sh"

# Enable and start all services
systemctl --user daemon-reload
systemctl --user enable forex-xvfb.service
systemctl --user enable forex-mt5.service
systemctl --user enable forex-bot.service

# Enable lingering so services run without login
sudo loginctl enable-linger "$USER"

systemctl --user start forex-xvfb.service
sleep 3
systemctl --user start forex-mt5.service
sleep 25
systemctl --user start forex-bot.service

echo ""
echo "============================================================"
echo " Setup complete! Everything will auto-start on reboot."
echo "============================================================"
echo ""
echo " Useful commands:"
echo "   Watch live logs:  tail -f $LOG_DIR/forex_auto.log"
echo "   Check status:     systemctl --user status forex-bot"
echo "   Stop bot:         systemctl --user stop forex-bot"
echo "   Restart all:      systemctl --user restart forex-mt5 forex-bot"
echo "============================================================"
