# TradingAgents — Complete Setup Guide
## Exness MT5 Live Trading on Linux VPS (US Stock CFDs)

**Target:** Trade US Stock CFDs (#NVDA, #AAPL, #TSLA) via Exness MT5  
**Capital:** $100 (Standard Account)  
**AI Engine:** TradingAgents + DeepSeek LLM  
**Platform:** Linux VPS + Wine + MT5  

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Requirements](#2-requirements)
3. [Exness Account Setup](#3-exness-account-setup)
4. [VPS Linux Setup](#4-vps-linux-setup)
5. [Wine + MT5 Installation](#5-wine--mt5-installation)
6. [Python Environment Setup](#6-python-environment-setup)
7. [TradingAgents Installation](#7-tradingagents-installation)
8. [Configuration](#8-configuration)
9. [Running the System](#9-running-the-system)
10. [Trading Guide](#10-trading-guide)
11. [Risk Management](#11-risk-management)
12. [Sri Lanka Trading Schedule](#12-sri-lanka-trading-schedule)
13. [Troubleshooting](#13-troubleshooting)
14. [Important Warnings](#14-important-warnings)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Linux VPS                             │
│                                                         │
│  ┌──────────────────┐    ┌──────────────────────────┐  │
│  │   Wine Layer     │    │   System Python           │  │
│  │                  │    │                           │  │
│  │  MT5 Terminal ◄──┼────┼── mt5linux server         │  │
│  │  (Exness login)  │    │                           │  │
│  │                  │    │  TradingAgents            │  │
│  │  Windows Python  │    │  + DeepSeek API           │  │
│  │  + MetaTrader5   │    │                           │  │
│  └──────────────────┘    └──────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

Flow:
  run_live.py
    → DeepSeek API (analysis)
    → MT5 via mt5linux (execution)
    → Exness (order placed)
```

### How It Works

1. `run_live.py` starts and runs **TradingAgents** analysis on the stock
2. **4 AI analysts** (market, news, fundamentals, social) research the stock
3. **Bull vs Bear** researchers debate the investment
4. **Portfolio Manager** makes final Buy/Hold/Sell decision
5. If **Buy or Sell** → order sent to **MT5** via mt5linux
6. MT5 places the order on **Exness** with stop-loss + take-profit
7. Portfolio state saved to JSON for tracking

---

## 2. Requirements

### Hardware (VPS Minimum)
| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Storage | 20 GB | 50 GB |
| OS | Ubuntu 20.04+ | Ubuntu 22.04 LTS |

### Accounts Needed
| Service | Cost | Purpose |
|---------|------|---------|
| Exness Standard (Demo) | Free | Paper trading |
| Exness Standard (Real) | $100 deposit | Live trading |
| DeepSeek API | ~$1/month | AI analysis |
| VPS (Contabo/Vultr) | $10-15/month | 24/7 operation |

### API Keys
- **DeepSeek API Key** → [platform.deepseek.com](https://platform.deepseek.com)
- **Exness MT5 credentials** → From your Exness Personal Area

---

## 3. Exness Account Setup

### 3.1 Register

1. Go to [exness.com](https://exness.com)
2. Click **"Open Account"**
3. Fill in details:
   - Email address
   - Password (strong — save it!)
   - Country: Sri Lanka
4. Verify your email

### 3.2 Create Demo Account

In your Personal Area:

1. Click **"Open New Account"**
2. Select:
   ```
   Account Type : Standard
   Platform     : MT5  ✅ (must be MT5, not MT4)
   Mode         : Demo ✅
   Currency     : USD
   Leverage     : 1:100
   ```
3. Click **"Create Account"**
4. Save your credentials:
   ```
   MT5 Login  : [your number]
   Password   : [your password]
   Server     : Exness-MT5Trial14 (or similar)
   ```
   > ⚠️ Save these — you will need them for the setup

### 3.3 Real Account (After Demo Success)

Only open real account after **1 month profitable demo trading**:

1. Complete KYC (NIC/Passport + Proof of Address)
2. Deposit $100 via USDT (TRC20) through Binance P2P
3. Open **Standard MT5** real account
4. Server will change to: `Exness-MT5Real8` or similar

---

## 4. VPS Linux Setup

### 4.1 Connect to VPS

```bash
ssh root@YOUR_VPS_IP
# Enter VPS password when prompted
```

### 4.2 System Update

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git wget curl nano screen htop
```

### 4.3 Create Trading User (Optional but Recommended)

```bash
adduser trader
usermod -aG sudo trader
su - trader
```

---

## 5. Wine + MT5 Installation

### 5.1 Install Wine

```bash
# Enable 32-bit architecture
sudo dpkg --add-architecture i386
sudo apt update

# Install Wine
sudo apt install -y wine64 wine32 winetricks cabextract

# Verify installation
wine --version
# Expected: wine-8.x.x or higher
```

### 5.2 Configure Wine

```bash
# Initialize Wine prefix
WINEARCH=win64 WINEPREFIX=~/.wine winecfg
```
> A window opens → Set Windows Version to **Windows 10** → OK

### 5.3 Install Required Windows Libraries

```bash
winetricks vcrun2019 vcrun2022 dotnet48
```
> This takes 5-10 minutes

### 5.4 Download MT5

```bash
cd ~
wget -O mt5setup.exe \
  "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
```

### 5.5 Install MT5 Under Wine

```bash
wine mt5setup.exe
```

> Installation wizard opens:
> 1. Click **Next**
> 2. Accept License Agreement
> 3. Click **Install**
> 4. Wait for completion (~2-3 minutes)
> 5. Click **Finish**

### 5.6 Launch MT5 and Login

```bash
# Start MT5 in background
wine ~/.wine/drive_c/Program\ Files/MetaTrader\ 5/terminal64.exe &

# Wait 10 seconds for it to load
sleep 10
```

In the MT5 window that opens:
1. Go to **File → Login to Trade Account**
2. Enter:
   ```
   Login    : 415672839
   Password : [your password]
   Server   : Exness-MT5Trial14
   ```
3. Click **Login**
4. You should see your balance at the bottom: `Balance: 10,000.00`
5. Minimize MT5 (do NOT close it)

### 5.7 Add Stocks to MarketWatch

In MT5:
1. Press **Ctrl+M** to open Market Watch
2. Right-click → **Show All**
3. Find and add: `#NVDA`, `#AAPL`, `#TSLA`, `#MSFT`, `#META`

### 5.8 Install Windows Python Inside Wine

```bash
# Download Python 3.10 Windows installer
wget -O ~/python-win.exe \
  "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"

# Install inside Wine
wine ~/python-win.exe
```

> In installer:
> 1. ✅ Check **"Add Python 3.10 to PATH"**
> 2. Click **"Install Now"**
> 3. Wait for completion
> 4. Click **Close**

### 5.9 Install MetaTrader5 Package Inside Wine

```bash
# Find Wine Python path
WINE_PYTHON=$(find ~/.wine -name "python.exe" 2>/dev/null | head -1)
echo "Wine Python: $WINE_PYTHON"

# Install MetaTrader5 package
wine "$WINE_PYTHON" -m pip install MetaTrader5

# Verify
wine "$WINE_PYTHON" -c "import MetaTrader5; print('MT5 package OK')"
# Expected: MT5 package OK ✅
```

---

## 6. Python Environment Setup

### 6.1 Install System Python Packages

```bash
# Install pip if needed
sudo apt install -y python3-pip python3-venv

# Create virtual environment
cd ~
python3 -m venv trading_env
source trading_env/bin/activate

# Install mt5linux and other dependencies
pip install mt5linux python-dotenv requests
```

### 6.2 Start mt5linux Server

> **This must be running whenever you trade**

```bash
# Find Wine Python
WINE_PYTHON=$(find ~/.wine -name "python.exe" 2>/dev/null | head -1)

# Start server in a screen session (keeps running after SSH disconnect)
screen -S mt5server

wine "$WINE_PYTHON" -c "
from mt5linux import server
server.run(host='localhost', port=18812)
"
```

> Expected output:
> ```
> MetaTrader5 server started on localhost:18812
> Waiting for connections...
> ```

Press **Ctrl+A** then **D** to detach from screen (server keeps running)

### 6.3 Test Connection

```bash
source ~/trading_env/bin/activate

python3 - << 'EOF'
from mt5linux import MetaTrader5 as MT5
mt5 = MT5(host='localhost', port=18812)

if mt5.initialize():
    info = mt5.account_info()
    print(f"✅ Connected!")
    print(f"   Login   : {info.login}")
    print(f"   Balance : ${info.balance:,.2f}")
    print(f"   Server  : {info.server}")
    mt5.shutdown()
else:
    print(f"❌ Failed: {mt5.last_error()}")
EOF
```

Expected:
```
✅ Connected!
   Login   : 415672839
   Balance : $10,000.00
   Server  : Exness-MT5Trial14
```

---

## 7. TradingAgents Installation

### 7.1 Clone Repository

```bash
source ~/trading_env/bin/activate
cd ~
git clone https://github.com/dusharakalubowila/TradingAgents.git
cd TradingAgents
```

### 7.2 Install Dependencies

```bash
pip install -e .
pip install python-dotenv langgraph langchain-openai yfinance pandas stockstats
```

### 7.3 Verify Installation

```bash
python3 -c "
from tradingagents.graph.trading_graph import TradingAgentsGraph
print('✅ TradingAgents imported successfully')
"
```

---

## 8. Configuration

### 8.1 Create .env File

```bash
cd ~/TradingAgents
cat > .env << 'EOF'
# DeepSeek API (cheap, high quality)
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# Exness MT5 Demo Credentials
MT5_LOGIN=415672839
MT5_PASSWORD=your_mt5_password
MT5_SERVER=Exness-MT5Trial14
EOF
```

> ⚠️ Never commit .env to GitHub — it's in .gitignore

### 8.2 Get DeepSeek API Key

1. Go to [platform.deepseek.com](https://platform.deepseek.com)
2. Sign up (free)
3. Go to **API Keys** → **Create new key**
4. Copy key → paste into `.env`

### 8.3 Verify Configuration

```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('DeepSeek Key:', 'SET ✅' if os.getenv('DEEPSEEK_API_KEY') else 'MISSING ❌')
print('MT5 Login   :', os.getenv('MT5_LOGIN', 'MISSING ❌'))
print('MT5 Server  :', os.getenv('MT5_SERVER', 'MISSING ❌'))
"
```

---

## 9. Running the System

### 9.1 Analysis Only (No Trade)

```bash
cd ~/TradingAgents
source ~/trading_env/bin/activate

python3 run_live.py --symbol "#NVDA"
```

Output:
```
============================================================
  TradingAgents Analysis
  Symbol   : NVDA  (Exness: #NVDA)
  Date     : 2026-05-04
  Provider : deepseek / deepseek-chat
  Analysts : market, social, news, fundamentals
============================================================

Running analysis… (3-8 minutes)

============================================================
  DECISION: Buy
============================================================

**Rating**: Buy
**Executive Summary**: Strong momentum with AI chip demand...
```

### 9.2 Dry Run (Preview Trade Without Executing)

```bash
python3 run_live.py --symbol "#NVDA" --execute --dry-run
```

Output:
```
============================================================
  DRY RUN — no order sent
  Symbol    : #NVDA
  Signal    : Buy
  Balance   : $100.00
  Risk/trade : 2%  ($2.00 max loss)
  Entry     : 127.50
  Stop-loss : 125.20
============================================================
```

### 9.3 Live Demo Trade

```bash
python3 run_live.py \
  --symbol "#NVDA" \
  --execute \
  --mt5-login 415672839 \
  --mt5-password "Dkk@20020922" \
  --mt5-server "Exness-MT5Trial14"
```

Or using .env (recommended):

```bash
python3 run_live.py --symbol "#NVDA" --execute
```

### 9.4 All Available Options

```bash
python3 run_live.py --help

Options:
  --symbol          Stock CFD symbol (default: #NVDA)
  --date            Analysis date YYYY-MM-DD (default: today)
  --provider        LLM provider (default: deepseek)
  --execute         Place real trade via MT5
  --dry-run         Preview trade without executing
  --balance         Starting balance (default: 100.0)
  --risk-pct        Risk per trade % (default: 2.0)
  --max-daily-loss-pct  Daily loss limit % (default: 5.0)
  --max-drawdown-pct    Max drawdown % (default: 20.0)
  --max-positions   Max open trades (default: 3)
  --tp-rr           Take profit ratio (default: 2.0)
  --no-session-filter   Skip session time check
  --no-news-filter      Skip news event check
```

### 9.5 Run Multiple Stocks

```bash
# Analyze all 3 stocks
for STOCK in "#NVDA" "#AAPL" "#TSLA"; do
    echo "Analyzing $STOCK..."
    python3 run_live.py --symbol "$STOCK" --execute
    sleep 60  # wait 1 minute between runs
done
```

### 9.6 Schedule Daily Runs (Cron)

```bash
# Open crontab
crontab -e

# Run NVDA analysis every weekday at 19:00 LKT (13:30 UTC)
30 13 * * 1-5 cd ~/TradingAgents && source ~/trading_env/bin/activate && python3 run_live.py --symbol "#NVDA" --execute >> ~/logs/trading.log 2>&1
```

---

## 10. Trading Guide

### 10.1 Best Stocks to Trade

| Stock | Why | Typical Spread |
|-------|-----|---------------|
| **#NVDA** | High AI demand, lots of news | ~$0.32 |
| **#AAPL** | Stable, good data | ~$0.13 |
| **#TSLA** | High volatility, lots of news | ~$0.25 |
| **#META** | Strong fundamentals | ~$0.20 |
| **#MSFT** | Stable, AI exposure | ~$0.53 |

### 10.2 Reading the Decision

| Signal | Meaning | Action |
|--------|---------|--------|
| **Buy** | Strong positive signal | Opens BUY order |
| **Overweight** | Moderate positive | Opens BUY order |
| **Hold** | Neutral | No trade placed |
| **Underweight** | Moderate negative | Opens SELL order |
| **Sell** | Strong negative signal | Opens SELL order |

### 10.3 Understanding the Output

```
**Rating**: Buy
                ↑ Main decision

**Executive Summary**: Enter long on NVDA at current levels...
                        ↑ What to do and why

**Investment Thesis**: AI chip demand accelerating...
                        ↑ Detailed reasoning

**Price Target**: 145.00
                   ↑ Where agent thinks price is going

**Time Horizon**: 2-4 weeks
                   ↑ How long to hold
```

### 10.4 Monitor Open Trades

In MT5 terminal:
1. Click **Trade** tab at bottom
2. See all open positions
3. Monitor profit/loss in real time

### 10.5 Close Trade Manually

In MT5:
1. Right-click on the trade
2. Click **Close Position**
3. Confirm

> **⚠️ IMPORTANT: Close all positions before 01:30 LKT (US market close)**

---

## 11. Risk Management

### 11.1 Built-in Protections

| Protection | Setting | What it does |
|-----------|---------|-------------|
| Risk per trade | 2% ($2) | Max loss on single trade |
| Daily loss limit | 5% ($5) | Stops trading after $5 loss/day |
| Max drawdown | 20% ($20) | Pauses if balance drops to $80 |
| Max positions | 3 | Never more than 3 open trades |
| News filter | 30 min | Skips trades before NFP, CPI etc. |
| Session filter | US hours | Only trades during market hours |

### 11.2 Position Sizing Example

```
Account balance : $100
Risk per trade  : 2% = $2
NVDA price      : $127.50
Stop loss       : $125.00 (distance = $2.50)

Lot size = $2 / $2.50 = 0.80 lots
         = 0.80 shares of NVDA

Max loss on this trade = 0.80 × $2.50 = $2.00 ✅
```

### 11.3 Golden Rules

```
✅ Always use stop loss
✅ Never risk more than 2% per trade
✅ Close all trades before 01:30 LKT
✅ Never trade before high-impact news (NFP, CPI)
✅ Check demo results for 1 month before real money
✅ Never deposit money you cannot afford to lose
```

---

## 12. Sri Lanka Trading Schedule

```
US Market Hours → Sri Lanka Time (LKT = UTC+5:30)

Pre-market    10:00 UTC = 15:30 LKT
Market opens  13:30 UTC = 19:00 LKT  ← Best entry time
Market closes 20:00 UTC = 01:30 LKT  ← Close all trades!

Recommended workflow:
  19:00 LKT → Run analysis, enter trade
  20:00 LKT → Check open positions
  01:00 LKT → Close all trades (30min before close)
  01:30 LKT → Market closes
```

### High-Impact News Times (LKT)

| Event | Typical Time (LKT) | Impact |
|-------|-------------------|--------|
| Non-Farm Payrolls (NFP) | 18:30 LKT (1st Friday) | 🔴 Very High |
| CPI Inflation | 18:30 LKT | 🔴 Very High |
| Fed Rate Decision | 02:00 LKT | 🔴 Very High |
| GDP Data | 18:30 LKT | 🟠 High |
| Earnings Reports | Varies | 🟠 High |

> System automatically skips trades 30 minutes before these events

---

## 13. Troubleshooting

### MT5 Connection Failed

```bash
# Check if MT5 is running
ps aux | grep terminal64

# Restart MT5
wine ~/.wine/drive_c/Program\ Files/MetaTrader\ 5/terminal64.exe &
sleep 15

# Check mt5linux server
screen -r mt5server
# Should show: "Waiting for connections..."
```

### mt5linux Server Not Running

```bash
# Check if server is running
screen -ls
# Look for: mt5server

# Restart if needed
screen -S mt5server
WINE_PYTHON=$(find ~/.wine -name "python.exe" | head -1)
wine "$WINE_PYTHON" -c "from mt5linux import server; server.run()"
# Ctrl+A then D to detach
```

### DeepSeek API Error

```bash
# Test API key
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('DEEPSEEK_API_KEY')
print('Key set:', bool(key))
print('Key starts with sk-:', key.startswith('sk-') if key else False)
"
```

### Order Rejected by MT5

Common reasons:
```
❌ Market closed        → Check trading hours (19:00-01:30 LKT)
❌ Invalid volume       → Min lot size issue
❌ Not enough margin    → Balance too low for position
❌ Symbol not found     → Add #NVDA to MT5 MarketWatch
❌ Wrong filling mode   → Auto-retried by executor ✅
```

### Analysis Takes Too Long

```bash
# Reduce debate rounds for faster analysis
python3 run_live.py --symbol "#NVDA" \
  --deep-model "deepseek-chat" \
  --quick-model "deepseek-chat"
```

### Portfolio State Out of Sync

```bash
# Reset portfolio state
rm ~/.tradingagents/portfolio/state.json
python3 run_live.py --symbol "#NVDA"
# Will create fresh state
```

### Logs

```bash
# View trading logs
cat ~/.tradingagents/logs/*/TradingAgentsStrategy_logs/*.json | python3 -m json.tool

# View portfolio state
cat ~/.tradingagents/portfolio/state.json | python3 -m json.tool
```

---

## 14. Important Warnings

### Legal Warning (Sri Lanka)

> ⚠️ Forex and CFD trading by Sri Lanka residents is technically not permitted  
> under the Foreign Exchange Act. Enforcement at the individual retail level  
> has historically been rare, but the legal risk is non-zero.  
> This system is provided for educational purposes.  
> You trade at your own legal and financial risk.

### Financial Risk Warning

> ⚠️ CFD trading involves significant risk of loss.  
> $100 is a very small account — you can lose it entirely.  
> Never deposit money you cannot afford to lose.  
> Always test on demo for at least 1 month before real money.  
> Past performance of the AI analysis does not guarantee future results.

### Security Warning

> ⚠️ Never share your MT5 password or API keys publicly.  
> Keep your .env file private — it is excluded from git.  
> Use strong, unique passwords for your Exness account.  
> Enable 2FA on your Exness Personal Area.

---

## Quick Reference Card

```bash
# Start everything (run in order)
wine ~/.wine/.../terminal64.exe &          # 1. Start MT5
screen -r mt5server                        # 2. Check mt5linux server
source ~/trading_env/bin/activate          # 3. Activate Python env
cd ~/TradingAgents                         # 4. Go to project

# Daily commands
python3 run_live.py --symbol "#NVDA"                          # Analysis only
python3 run_live.py --symbol "#NVDA" --execute --dry-run      # Preview trade
python3 run_live.py --symbol "#NVDA" --execute                # Live trade
python3 run_live.py --symbol "#AAPL" --execute                # Trade AAPL
python3 run_live.py --symbol "#TSLA" --execute --risk-pct 1   # Trade TSLA, 1% risk

# Check portfolio
cat ~/.tradingagents/portfolio/state.json | python3 -m json.tool

# Update code
git pull origin main
```

---

## Support

- **GitHub Repository:** [github.com/dusharakalubowila/TradingAgents](https://github.com/dusharakalubowila/TradingAgents)
- **DeepSeek API Docs:** [platform.deepseek.com/docs](https://platform.deepseek.com/docs)
- **Exness Help:** [get.exness.help](https://get.exness.help)
- **mt5linux Docs:** [github.com/lucas-campagna/mt5linux](https://github.com/lucas-campagna/mt5linux)

---

*Last updated: May 2026*  
*Built with TradingAgents framework + Exness MT5 integration*
