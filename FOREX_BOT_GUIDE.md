# TradingAgents Forex Bot — Complete Guide

> **Branch:** `forex-strategy`  
> **Entry point:** `run_forex.py`  
> **Account:** Exness Standard | Demo login: 415672839  
> **Capital:** $100 | Risk: 1% per trade ($1 max loss)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [How the Bot Makes Decisions](#2-how-the-bot-makes-decisions)
3. [Strategy 1 — London Breakout](#3-strategy-1--london-breakout)
4. [Strategy 2 — ICT / Smart Money Concepts](#4-strategy-2--ict--smart-money-concepts)
5. [Strategy 3 — EMA Hybrid](#5-strategy-3--ema-hybrid)
6. [LLM Sentiment Gate](#6-llm-sentiment-gate)
7. [Risk Management Rules](#7-risk-management-rules)
8. [Best Pairs & When to Trade](#8-best-pairs--when-to-trade)
9. [Sri Lanka Trading Schedule](#9-sri-lanka-trading-schedule)
10. [Installation on Linux VPS](#10-installation-on-linux-vps)
11. [Configuration](#11-configuration)
12. [Running the Bot](#12-running-the-bot)
13. [Understanding the Output](#13-understanding-the-output)
14. [Performance Expectations](#14-performance-expectations)
15. [Troubleshooting](#15-troubleshooting)
16. [Safety Rules — Read Before Going Live](#16-safety-rules--read-before-going-live)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     run_forex.py                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            STEP 1: Pre-trade Filters                 │  │
│  │   Session check  →  News calendar check              │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         STEP 2: Technical Strategy Engine            │  │
│  │                                                      │  │
│  │  London Breakout  +  ICT/SMC  +  EMA Hybrid         │  │
│  │         ↓                ↓             ↓             │  │
│  │              Pick highest confidence signal          │  │
│  │         (bonus if 2+ strategies agree = confluence)  │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         STEP 3: LLM Sentiment Gate                   │  │
│  │                                                      │  │
│  │  DeepSeek AI reads market data + macro news          │  │
│  │  Technical BUY  must match  LLM Buy/Overweight       │  │
│  │  Technical SELL must match  LLM Sell/Underweight     │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         STEP 4: Execution via MT5                    │  │
│  │                                                      │  │
│  │  Risk check  →  Lot sizing  →  Order placement      │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### What makes this different from a simple indicator bot

A simple EA (Expert Advisor) fires on a single indicator signal. This bot layers **four independent confirmation systems** before placing a trade:

1. **Time filter** — only trade in high-liquidity windows
2. **News filter** — skip 30 min before major economic events
3. **Technical confluence** — 3 independent strategies must agree
4. **LLM sentiment** — AI reads the macro environment

The result: far fewer trades, but much higher quality entries.

---

## 2. How the Bot Makes Decisions

### Signal flow (simplified)

```
Market opens
     ↓
Is it a good trading session?  →  NO → Exit, wait
     ↓ YES
Is there high-impact news soon? →  YES → Exit, wait
     ↓ NO
Run London Breakout strategy    →  BUY / SELL / WAIT
Run ICT/SMC strategy            →  BUY / SELL / WAIT
Run EMA Hybrid strategy         →  BUY / SELL / WAIT
     ↓
Any actionable signals?         →  NO → Exit, no trade
     ↓ YES
2 or more strategies agree?     →  YES → confidence boost +10%
     ↓
Run DeepSeek LLM analysis       →  Buy / Hold / Sell
     ↓
Technical signal agrees with LLM? →  NO → Exit, no trade
     ↓ YES
Risk guard: daily loss limit OK?   →  NO → Exit, daily limit hit
Risk guard: max positions OK?      →  NO → Exit, too many open trades
     ↓ YES
Calculate lot size (1% risk / stop distance)
     ↓
Place order on MT5
```

### Signal confidence scores

| Scenario | Confidence |
|---|---|
| Single strategy signal | 0.58 – 0.75 |
| ADX > 30 (strong trend) | +0.08 bonus |
| 2+ strategies agree | +0.10 bonus |
| Maximum possible | 1.00 (100%) |

A trade is placed **only when**:
- Confidence ≥ 0.55
- LLM agrees with direction
- Risk limits not exceeded

---

## 3. Strategy 1 — London Breakout

### Concept

The Asian session (Tokyo/Singapore) is quiet — GBPUSD trades in a tight range for ~9 hours. When London banks open, they push price through one side of that range with strong momentum. We trade that breakout.

### Why it works

- GBP is barely traded in Asia → genuine range forms overnight
- London open creates a real directional "push" (not random noise)
- The Asian range acts as institutional support/resistance
- Documented win rate: **58–65% on GBPUSD** with filters

### Entry rules

```
1. Time: 07:00–09:00 UTC (12:30–14:30 LKT)

2. Identify Asian range:
   - Asian session = 22:00 UTC (yesterday) → 07:00 UTC (today)
   - Asian HIGH = highest candle high across all H1 candles in that window
   - Asian LOW  = lowest candle low across all H1 candles in that window

3. Range filter (skip if outside):
   - Range must be 20–80 pips wide
   - Too narrow (<20 pips) = no clear range formed
   - Too wide (>80 pips) = already moved, too late

4. Entry trigger:
   - BUY:  current price closes above Asian HIGH + 2 pip buffer
   - SELL: current price closes below Asian LOW  - 2 pip buffer
```

### Stop loss & take profit

```
BUY trade:
  Stop Loss   = Asian HIGH - (50% of range width)
                → Protected in the upper half of the range
  Take Profit = Entry + (1.5 × range width)
                → Risk:Reward ≈ 1:2+

SELL trade:
  Stop Loss   = Asian LOW + (50% of range width)
  Take Profit = Entry - (1.5 × range width)
```

**Example (GBPUSD):**
```
Asian HIGH = 1.27500
Asian LOW  = 1.27100
Range = 40 pips

BUY trigger at: 1.27520 (2 pip above HIGH)
Stop Loss:   1.27300 (mid-range, 22 pips risk)
Take Profit: 1.27820 (1.5× range above entry, 30 pips reward)
Risk:Reward = 1 : 1.36  (minimum; usually better)
```

### Hard exit rule

**Close ALL London Breakout positions by 12:00 UTC (17:30 LKT).**

After 12:00 UTC the London momentum fades. Holding longer degrades win rate significantly.

### Best days

- **Best:** Tuesday, Wednesday, Thursday
- **Avoid:** Monday (low London liquidity), Friday (early close risk)

---

## 4. Strategy 2 — ICT / Smart Money Concepts

### Concept

ICT (Inner Circle Trader) methodology reverse-engineers how institutional banks (JPMorgan, Deutsche Bank, Citibank) move the market. Banks leave footprints in the price structure:

- **Fair Value Gaps (FVG):** A three-candle pattern where price moved so fast it left an "unfilled" gap. Institutions re-enter to fill these gaps.
- **Order Blocks (OB):** The last candle before a major move — this is where institutions placed their orders. Price often returns to these levels.
- **Break of Structure (BOS):** When price breaks a previous swing high/low — confirms trend direction.

### Why it works

- Based on actual institutional order flow mechanics
- Works on all major pairs and XAUUSD (gold)
- Only trades inside "kill zones" when institutions are active
- Documented win rate: **58–72%** with proper BOS confirmation

### Kill zones (when institutions trade)

| Kill Zone | UTC | LKT | Best Pairs |
|---|---|---|---|
| London Open | 02:00–05:00 | 07:30–10:30 | EURUSD, GBPUSD |
| New York Open | 12:00–15:00 | 17:30–20:30 | EURUSD, XAUUSD |
| London Close | 15:00–17:00 | 20:30–22:30 | Reversals only |

**The bot only runs ICT analysis inside London or NY kill zones.**

### Entry rules (Long setup)

```
1. Time: inside London KZ (02–05 UTC) or NY KZ (12–15 UTC)

2. Break of Structure (BOS):
   - A recent H1 candle broke above a previous swing high
   - This confirms BULLISH institutional intent

3. Fair Value Gap below current price:
   - A bullish FVG exists (three-candle imbalance, candle 1 and 3 wicks don't overlap)
   - FVG is below current price (not yet filled)

4. Retest:
   - Current price has retraced INTO the FVG zone
   - FVG bottom ≤ current price ≤ FVG top

5. → Enter BUY at market
```

### Entry rules (Short setup)

Mirror of above: bearish BOS + bearish FVG above price + price retracing into FVG.

### Stop loss & take profit

```
Long:
  Stop Loss   = FVG bottom - 5 pips (FVG invalidated if price goes here)
  Take Profit = Entry + 2 × (Entry - Stop Loss)   [2:1 RR minimum]

Short:
  Stop Loss   = FVG top + 5 pips
  Take Profit = Entry - 2 × (Stop Loss - Entry)
```

### Required package

The ICT strategy uses the `smartmoneyconcepts` Python library:

```bash
pip install smartmoneyconcepts
```

If not installed, the strategy logs a warning and returns WAIT (does not crash the bot).

---

## 5. Strategy 3 — EMA Hybrid

### Concept

Combines a trend-defining EMA with a momentum entry and multiple filters to reduce false signals. Used by professional algo traders. The key insight: **EMA crossovers alone have a 57% false signal rate — but combining them with a trend filter and RSI gate brings win rates to 52–60%.**

### Why it works

- 200 EMA on H1 provides the macro trend direction
- 9/21 EMA crossover on M15 provides precise entry timing
- RSI filter prevents chasing overbought/oversold moves
- ADX filter completely skips ranging markets (no trend = no trade)

### Entry rules (Long)

```
1. Time: 07–11 UTC (12:30–16:30 LKT) or 13–16 UTC (18:30–21:30 LKT)

2. Trend check (H1):
   - H1 close > 200 EMA → BULL trend → long setups only
   - H1 close < 200 EMA → BEAR trend → short setups only

3. ADX filter (H1):
   - ADX(14) must be > 20
   - If ADX < 20 = ranging market → SKIP (no trade)
   - ADX > 30 = very strong trend → confidence boost

4. Entry signal (M15):
   - 9 EMA crosses ABOVE 21 EMA (golden cross on M15)
   - Trend is BULL (from step 2)

5. RSI gate (M15):
   - RSI(14) must be between 45–68
   - Below 45 = momentum not yet confirmed
   - Above 68 = already overbought, too late to enter

6. → Enter BUY at market close of crossover candle
```

### Entry rules (Short)

```
- 9 EMA crosses BELOW 21 EMA (death cross on M15)
- Trend is BEAR (H1 price < 200 EMA)
- RSI(14) between 32–55
- ADX > 20
→ Enter SELL
```

### Stop loss & take profit

```
Stop Loss   = Entry - (1.5 × ATR(14) on M15)   [ATR-based, adapts to volatility]
Take Profit = Entry + (3.0 × ATR(14) on M15)   [≈ 1:2 RR]
```

ATR-based stops automatically widen during volatile sessions and tighten during calm markets.

### Required package

```bash
pip install ta
```

---

## 6. LLM Sentiment Gate

### What it does

After the technical strategies produce a signal, the bot runs the **TradingAgents multi-agent LLM analysis** as a final confirmation. This uses DeepSeek AI (cost: ~$0.002 per analysis) to:

- Analyze the latest price action and technical indicators
- Read recent macroeconomic news (central bank decisions, GDP, CPI, etc.)
- Produce a directional rating: **Buy / Overweight / Hold / Underweight / Sell**

### Gate logic

```
Technical signal = BUY
  LLM says Buy or Overweight  →  PROCEED
  LLM says Hold               →  BLOCKED
  LLM says Underweight or Sell →  BLOCKED

Technical signal = SELL
  LLM says Sell or Underweight →  PROCEED
  LLM says Hold               →  BLOCKED
  LLM says Buy or Overweight  →  BLOCKED
```

### Two analysts run for forex

| Analyst | What it does |
|---|---|
| Market Analyst | Reads price data and technical indicators (EMA, RSI, MACD, Bollinger, ATR) |
| News Analyst | Reads recent macroeconomic news and central bank headlines |

*Fundamentals and Social Media analysts are not used for forex (no company balance sheets, social sentiment less relevant).*

### Skipping the LLM gate

Add `--no-llm-gate` to skip and trade on technical signal only. This is:
- **Faster** (saves 2–4 minutes)
- **Cheaper** (no API call)
- **Less accurate** (removes the macro filter)

Use `--no-llm-gate` only during testing or when you trust the technical setup strongly.

---

## 7. Risk Management Rules

### Position sizing formula

```
Lot size = Risk amount ÷ (Stop distance in pips × Pip value per lot)

Where:
  Risk amount = Account balance × Risk % per trade
              = $100 × 1% = $1.00

  Pip value per lot:
    EURUSD / GBPUSD = $10 per pip per standard lot
                    = $0.10 per pip per 0.01 lot (micro)

Example (GBPUSD, 20 pip stop):
  Lot size = $1.00 ÷ (20 × $10) = 0.005 lots → rounded to 0.01 lots (minimum)
```

### Hard limits (cannot be changed at runtime without editing risk_guard.py)

| Limit | Default | What happens when hit |
|---|---|---|
| Risk per trade | 1% ($1) | Order not placed |
| Daily loss limit | 3% ($3) | Bot stops trading for the day |
| Max drawdown | 15% ($15 from peak) | Bot pauses, alerts you |
| Max open positions | 2 | No new trades opened |
| Same-direction duplicate | Blocked | Won't open 2nd long on same pair |

### Why 1% not 2%?

Forex is riskier than stocks for this bot because:
- Spreads are a higher percentage of the move
- Forex has 24h exposure (news can hit overnight)
- The LLM analyst quality is lower for forex (no fundamentals)

1% risk = $1 max loss per trade. At this level, you can have **15 losing trades in a row** before losing 15% of your account.

---

## 8. Best Pairs & When to Trade

### Pair selection guide

| Pair | Strategy | Spread (Exness) | Daily Range | Notes |
|---|---|---|---|---|
| **GBPUSD** | London Breakout | 0.3–0.8 pips | 80–120 pips | Best for London Breakout |
| **EURUSD** | ICT/SMC, EMA | 0.1–0.3 pips | 50–80 pips | Tightest spreads, most liquid |
| **XAUUSD** | ICT/SMC, EMA | 15–25 points | $15–$35/oz | Highest pip value, more volatile |
| AUDUSD | EMA only | 0.3–0.6 pips | 40–60 pips | Less volatile, safer |
| USDJPY | EMA only | 0.2–0.5 pips | 50–80 pips | Works during Asian session too |

### Recommended starting pair

**Start with EURUSD.** Lowest spreads, most liquid, cleanest charts, best data quality from yfinance.

After 2 weeks of demo trading, add GBPUSD for London Breakout.

Only add XAUUSD (gold) once you are profitable on EURUSD — gold is highly volatile and requires wider stops.

---

## 9. Sri Lanka Trading Schedule

**Sri Lanka = UTC+5:30 (LKT)**

### London Breakout window (GBPUSD)

| UTC | LKT | Action |
|---|---|---|
| 22:00 | 03:30 | Asian range starts forming |
| 07:00 | 12:30 | **Entry window opens** |
| 09:00 | 14:30 | Entry window closes |
| 12:00 | 17:30 | **Hard exit — close all London Breakout trades** |

**You need to be available 12:30–14:30 LKT to monitor entries.**

### ICT Kill Zones

| Kill Zone | UTC | LKT | Best pair |
|---|---|---|---|
| London Open | 02:00–05:00 | **07:30–10:30** | EURUSD, GBPUSD |
| NY Open | 12:00–15:00 | **17:30–20:30** | EURUSD, XAUUSD |

### EMA Hybrid windows

| UTC | LKT |
|---|---|
| 07:00–11:00 | 12:30–16:30 |
| 13:00–16:00 | 18:30–21:30 |

### Recommended daily routine

```
07:30 LKT  → Check ICT London kill zone (EURUSD/GBPUSD)
12:30 LKT  → Check London Breakout (GBPUSD) + EMA setups
14:30 LKT  → London Breakout entry window closes
17:30 LKT  → Close all London Breakout positions
17:30 LKT  → Check ICT NY kill zone (EURUSD/XAUUSD)
20:30 LKT  → ICT NY kill zone closes
21:30 LKT  → EMA window closes. Done for the day.
```

---

## 10. Installation on Linux VPS

### Step 1 — Install system dependencies

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv wget
```

### Step 2 — Clone the forex branch

```bash
git clone -b forex-strategy https://github.com/dusharakalubowila/TradingAgents.git
cd TradingAgents
```

### Step 3 — Create Python environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 4 — Install Python packages

```bash
pip install -e ".[dev]"
pip install ta smartmoneyconcepts python-dotenv
```

### Step 5 — Create .env file

```bash
cat > .env << 'EOF'
DEEPSEEK_API_KEY=sk-84f465546ce140ab8c5e6f9b8f35f8e7

# Exness MT5 Demo
MT5_LOGIN=415672839
MT5_PASSWORD=Dkk@20020922
MT5_SERVER=Exness-MT5Trial14
EOF
```

### Step 6 — Install Wine + MT5 (for live execution)

```bash
# Add 32-bit support
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wine64 wine32 winetricks

# Download and install MT5 under Wine
wget "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
wine mt5setup.exe
# Log in with your Exness demo credentials when prompted
```

### Step 7 — Install Windows Python inside Wine (for mt5linux bridge)

```bash
wget https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
wine python-3.10.11-amd64.exe
# Check "Add Python to PATH" during install

wine python -m pip install MetaTrader5
```

### Step 8 — Start the MT5 bridge

```bash
# Terminal 1: keep this running
python -m mt5linux

# Terminal 2: run the bot
source venv/bin/activate
python run_forex.py --symbol EURUSD
```

### Verify installation

```bash
# Should print strategy analysis without errors
python run_forex.py --symbol EURUSD

# Should print dry-run execution details
python run_forex.py --symbol EURUSD --execute --dry-run \
  --mt5-login 415672839 --mt5-password Dkk@20020922 --mt5-server Exness-MT5Trial14
```

---

## 11. Configuration

### Command-line arguments

```
python run_forex.py [options]

SYMBOL:
  --symbol EURUSD       Forex pair (default: GBPUSD)
                        Options: EURUSD, GBPUSD, XAUUSD, AUDUSD, USDJPY

DATE:
  --date 2025-05-06     Analysis date (default: today)

LLM PROVIDER:
  --provider deepseek   LLM provider (default: deepseek)
                        Options: deepseek, openai, anthropic, google, ollama
  --no-llm-gate         Skip LLM confirmation, use technical signal only

EXECUTION:
  --execute             Place real trades via MT5
  --dry-run             Show what would happen without placing order

RISK:
  --balance 100.0       Account balance in USD (default: 100)
  --risk-pct 1.0        Risk per trade % (default: 1%)
  --max-daily-loss-pct  Daily loss limit % (default: 3%)
  --max-positions 2     Maximum concurrent open trades (default: 2)
  --tp-rr 2.0           Take-profit reward:risk ratio (default: 2.0)

FILTERS:
  --no-session-filter   Skip trading session check
  --no-news-filter      Skip high-impact news check

MT5 CONNECTION:
  --mt5-host localhost  MT5 server host (default: localhost)
  --mt5-port 18812      MT5 server port (default: 18812)
  --mt5-login           MT5 account login number
  --mt5-password        MT5 account password
  --mt5-server          MT5 broker server name
```

### Environment variables (.env file)

```env
DEEPSEEK_API_KEY=your_key_here

MT5_LOGIN=415672839
MT5_PASSWORD=Dkk@20020922
MT5_SERVER=Exness-MT5Trial14
```

### LLM provider cost comparison

| Provider | Model | Cost per analysis | Quality |
|---|---|---|---|
| **DeepSeek** | deepseek-chat | ~$0.002 | Very good |
| OpenAI | gpt-4.1 | ~$0.05 | Excellent |
| Anthropic | claude-sonnet-4-6 | ~$0.03 | Excellent |
| Google | gemini-2.5-flash | ~$0.003 | Good |
| Ollama | llama3.1:8b (local) | Free | Moderate |

**Recommended: DeepSeek** — best cost/quality ratio for a $100 account.

---

## 12. Running the Bot

### Analysis only (no trade, no MT5 needed)

```bash
python run_forex.py --symbol EURUSD
```

Runs all 3 strategies and LLM analysis. Shows what signal would be produced. No order is placed. Good for daily market checking.

### Dry run (preview trade details)

```bash
python run_forex.py --symbol GBPUSD --execute --dry-run \
  --mt5-login 415672839 --mt5-password Dkk@20020922 --mt5-server Exness-MT5Trial14
```

Shows exactly what trade would be placed (symbol, direction, lot size, entry, SL, TP) without sending it to MT5.

### Live trade

```bash
python run_forex.py --symbol EURUSD --execute \
  --mt5-login 415672839 --mt5-password Dkk@20020922 --mt5-server Exness-MT5Trial14
```

### Fast mode (technical signals only, skip LLM)

```bash
python run_forex.py --symbol EURUSD --execute --no-llm-gate \
  --mt5-login 415672839 --mt5-password Dkk@20020922 --mt5-server Exness-MT5Trial14
```

### XAUUSD (gold)

```bash
python run_forex.py --symbol XAUUSD --execute
```

### Custom risk settings

```bash
# More conservative: 0.5% risk, 2% daily limit
python run_forex.py --symbol EURUSD --execute \
  --risk-pct 0.5 --max-daily-loss-pct 2.0

# More aggressive: 2% risk (not recommended on $100)
python run_forex.py --symbol EURUSD --execute \
  --risk-pct 2.0 --max-daily-loss-pct 5.0
```

### Automated cron job (run at London open every weekday)

```bash
# Edit crontab
crontab -e

# Add this line (runs at 07:00 UTC = 12:30 LKT, Mon–Fri)
0 7 * * 1-5 /home/user/TradingAgents/venv/bin/python /home/user/TradingAgents/run_forex.py --symbol GBPUSD --execute --mt5-login 415672839 --mt5-password Dkk@20020922 --mt5-server Exness-MT5Trial14 >> /home/user/trading.log 2>&1

# Also run at NY open (12:00 UTC = 17:30 LKT)
0 12 * * 1-5 /home/user/TradingAgents/venv/bin/python /home/user/TradingAgents/run_forex.py --symbol EURUSD --execute --mt5-login 415672839 --mt5-password Dkk@20020922 --mt5-server Exness-MT5Trial14 >> /home/user/trading.log 2>&1
```

---

## 13. Understanding the Output

### Example output for a BUY signal

```
============================================================
  TradingAgents FOREX Bot
============================================================
  Symbol   : GBPUSD  →  yfinance: GBPUSD=X
  Strategy : London Breakout (primary) + EMA Hybrid
============================================================

  Session : UTC: 07:15  |  LKT: 12:45  |  Session: London

============================================================
  Technical Strategy Analysis
============================================================
  Pair     : GBPUSD
  Time UTC : 07:15  |  LKT: 12:45

✅ [LONDON_BREAKOUT ] BUY   conf=0.68  Bullish breakout above 1.27500 | range=42.0 pips
⏳ [ICT_SMC         ] WAIT  conf=0.00  Not in ICT kill zone
✅ [EMA_HYBRID      ] BUY   conf=0.70  Golden cross M15 | BULL (1.27530 > EMA200 1.27200) | RSI 52 | ADX 28

  Strategy   : EMA_HYBRID
  Signal     : 🟢 BUY
  Confidence : 80%           ← boosted from 70% (2-strategy confluence +10%)
  Reason     : [2-strategy confluence] Golden cross M15 ...
  Entry      : 1.27545
  Stop-loss  : 1.27345
  Take-profit: 1.27945

============================================================
  LLM Sentiment Gate (Market + News Analysis)
============================================================
  LLM SIGNAL: Overweight

============================================================
  Gate Decision
============================================================
  Technical : BUY  (EMA_HYBRID)
  LLM       : Overweight
  Agreement : YES — proceed
============================================================

============================================================
  RESULT
============================================================
  TRADE PLACED
  Ticket     : 12345678
  Action     : BUY
  Volume     : 0.01 lots
  Price      : 1.27548
  Stop-loss  : 1.27348
  Take-profit: 1.27948
```

### What each section means

| Section | Meaning |
|---|---|
| `✅ BUY conf=0.68` | Strategy found a signal with 68% confidence |
| `⏳ WAIT conf=0.00` | Strategy found no signal right now |
| `[2-strategy confluence]` | Multiple strategies agreed, confidence boosted |
| `Agreement: YES` | LLM confirmed the technical signal |
| `Volume: 0.01 lots` | Minimum lot size (safest for $100) |

### When no trade is placed

```
  No technical signal at this time.

  Optimal times (LKT = Sri Lanka Time):
  London Breakout : 12:30–14:30 LKT  (entry only)
  ICT London KZ   : 07:30–10:30 LKT
  ICT NY KZ       : 17:30–20:30 LKT
  EMA windows     : 12:30–16:30 LKT  or  18:30–21:30 LKT
```

This is normal. **A good bot says WAIT more often than it trades.** Forcing trades outside optimal windows is how accounts blow up.

---

## 14. Performance Expectations

### Realistic monthly projections ($100 account, 1% risk)

| Scenario | Win Rate | Trades/month | Net Result |
|---|---|---|---|
| Poor market conditions | 48% | 12 | -$2.4 (–2.4%) |
| Average | 55% | 15 | +$8.5 (+8.5%) |
| Good conditions | 62% | 15 | +$14.1 (+14.1%) |
| Excellent (confluence) | 68% | 10 | +$11.6 (+11.6%) |

*Based on: 1:2 RR, $1 risk per trade, 15 trades/month*

### 6-month growth projection (55% win rate, 8.5%/month)

```
Month 0: $100.00
Month 1: $108.50
Month 2: $117.72
Month 3: $127.73
Month 4: $138.59
Month 5: $150.37
Month 6: $163.15
```

**Important:** These are projections, not guarantees. Forex trading involves real risk of loss.

### When to increase risk to 2%

Only increase risk to 2% after:
1. 3 consecutive profitable months on demo
2. 1 consecutive profitable month on live $100
3. Account has grown to at least $150

---

## 15. Troubleshooting

### "smartmoneyconcepts not installed"

```bash
pip install smartmoneyconcepts
```

If ICT/SMC fails silently, the London Breakout and EMA Hybrid strategies still run.

### "ta package not installed"

```bash
pip install ta
```

If EMA Hybrid fails, London Breakout and ICT/SMC still run.

### "Insufficient H1 data"

yfinance sometimes returns empty data for forex pairs. Try:
```bash
# Test the yfinance connection manually
python3 -c "import yfinance as yf; df = yf.download('GBPUSD=X', period='5d', interval='1h'); print(df.tail())"
```

If empty, wait 10 minutes and retry — yfinance has occasional rate limits.

### "Not in ICT kill zone"

This is expected outside 02–05 UTC and 12–15 UTC. The ICT strategy only fires during those windows. Use London Breakout (07–09 UTC) or EMA Hybrid (07–11 or 13–16 UTC) outside kill zones.

### "Cannot connect to MT5"

```bash
# Check mt5linux bridge is running
ps aux | grep mt5linux

# Restart bridge
python -m mt5linux

# Test connection
python3 -c "
from tradingagents.broker.mt5_client import MT5Client
mt5 = MT5Client()
result = mt5.initialize(login=415672839, password='Dkk@20020922', server='Exness-MT5Trial14')
print('Connected:', result)
"
```

### "Trade blocked — daily loss limit"

The bot stopped trading because you lost 3% ($3) in one day. This is working as intended.
- Wait until tomorrow for the daily limit to reset
- Or reduce position sizes and restart

### "Asian range too wide / narrow"

- Too narrow (<20 pips): GBPUSD traded in a very tight range overnight. No London Breakout today.
- Too wide (>80 pips): A news event moved GBPUSD during the Asian session. The breakout already happened. No trade.

Both are normal. Happens 2–3 times per week.

### LLM analysis fails / times out

```bash
# Test DeepSeek API
python3 -c "
import os
from openai import OpenAI
client = OpenAI(api_key=os.getenv('DEEPSEEK_API_KEY'), base_url='https://api.deepseek.com')
r = client.chat.completions.create(model='deepseek-chat', messages=[{'role':'user','content':'Hello'}])
print(r.choices[0].message.content)
"
```

If DeepSeek is down, use `--no-llm-gate` to trade on technical signals only.

---

## 16. Safety Rules — Read Before Going Live

### Demo first — minimum 4 weeks

**Do not use real money until:**
- [ ] MT5 connects and demo trades place correctly
- [ ] You have run the bot every trading day for 4 weeks
- [ ] You have at least 20 completed demo trades
- [ ] Your demo win rate is above 50%
- [ ] You understand every part of the output

### Never risk more than you can afford to lose

At $100, each trade risks $1. This is sustainable. If you fund with $500, the same 1% = $5 per trade. Risk scales with balance — the percentage stays the same.

### Check open positions before running again

The bot does not automatically close positions. Before running it again:

```bash
# Check what's open in MT5
python3 -c "
from tradingagents.broker.mt5_client import MT5Client
mt5 = MT5Client()
mt5.initialize(login=415672839, password='Dkk@20020922', server='Exness-MT5Trial14')
for p in mt5.positions_get():
    print(p)
mt5.shutdown()
"
```

### Always close before sleeping if using London Breakout

London Breakout positions must be closed by 12:00 UTC (17:30 LKT). If you run the bot at 07:00 UTC and go to sleep, you may miss the 12:00 UTC exit. **Set a phone alarm for 17:00 LKT.**

### High-impact news events

The news filter automatically blocks trades 30 minutes before:
- US Non-Farm Payrolls (first Friday of each month, 13:30 UTC)
- US CPI / Federal Reserve rate decisions
- UK CPI / Bank of England decisions
- ECB rate decisions

If the news filter is bypassed (`--no-news-filter`), be aware of these events.

### The bot is a decision support tool, not an autopilot

Even with all these systems, forex trading carries real risk. The bot improves your decision quality and enforces discipline — it does not guarantee profits. Monitor it, understand its decisions, and intervene if something looks wrong.

---

## Quick Reference Card

```
BEST PAIRS BY STRATEGY:
  London Breakout    → GBPUSD
  ICT/SMC            → EURUSD, XAUUSD
  EMA Hybrid         → EURUSD, XAUUSD, GBPUSD

BEST ENTRY TIMES (LKT):
  07:30–10:30  → ICT London Kill Zone
  12:30–14:30  → London Breakout entry window
  17:30–20:30  → ICT NY Kill Zone
  18:30–21:30  → EMA Hybrid

CRITICAL EXITS:
  17:30 LKT  → Close ALL London Breakout positions

COMMANDS:
  Analysis only:  python run_forex.py --symbol EURUSD
  Dry run:        python run_forex.py --symbol EURUSD --execute --dry-run
  Live trade:     python run_forex.py --symbol EURUSD --execute
  No LLM gate:    python run_forex.py --symbol EURUSD --execute --no-llm-gate

RISK DEFAULTS:
  Risk per trade  : 1% ($1 on $100)
  Daily loss limit: 3% ($3 on $100)
  Max positions   : 2
  Stop loss       : Strategy-calculated (ATR or range-based)
```

---

*Last updated: 2026-05-06 | Branch: forex-strategy | Bot version: 1.0*
