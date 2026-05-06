#!/usr/bin/env python3
"""
TradingAgents Forex Bot — World-Class Strategy Engine

Three institutional strategies running in parallel:
  1. London Breakout  → GBPUSD primary (07:00–09:00 UTC, exit 12:00 UTC)
  2. ICT/SMC          → EURUSD, XAUUSD (kill zones: 02–05 or 12–15 UTC)
  3. EMA Hybrid       → Any pair (07–11 UTC or 13–16 UTC)

LLM Gate: TradingAgents multi-agent analysis must AGREE with the
          technical signal before any trade is placed.

Win rates (realistic live):
  London Breakout (GBPUSD): 58–65%
  ICT/SMC (EURUSD):         58–72%
  EMA Hybrid:               52–60%

QUICK START
-----------
  Analysis only (no trade):
    python run_forex.py --symbol GBPUSD

  Preview what would happen (dry-run):
    python run_forex.py --symbol GBPUSD --execute --dry-run

  Live trade:
    python run_forex.py --symbol GBPUSD --execute

  Skip LLM confirmation (tech only, faster):
    python run_forex.py --symbol EURUSD --execute --no-llm-gate

Best pairs:
  GBPUSD   → London Breakout
  EURUSD   → ICT/SMC or EMA Hybrid
  XAUUSD   → ICT/SMC or EMA Hybrid (highest pip value)

Sri Lanka trading schedule:
  London Breakout entry → 12:30–14:30 LKT
  ICT London KZ        → 07:30–10:30 LKT
  ICT NY KZ            → 17:30–20:30 LKT
  EMA best windows     → 12:30–16:30 LKT  or  18:30–21:30 LKT

LINUX MT5 SETUP
---------------
  1. sudo apt install wine64 wine32 winetricks
  2. Install MT5 from Exness under Wine
  3. pip install mt5linux
  4. python -m mt5linux   (keep open in separate terminal)
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_forex")

# ── Provider defaults ─────────────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "deepseek":  ("deepseek-chat",          "deepseek-chat"),
    "openai":    ("gpt-4.1",                "gpt-4.1-mini"),
    "anthropic": ("claude-sonnet-4-6",      "claude-haiku-4-5-20251001"),
    "google":    ("gemini-2.5-pro",         "gemini-2.5-flash"),
    "ollama":    ("llama3.1:8b",            "llama3.1:8b"),
}

# Pairs and their best strategies (for display)
PAIR_PROFILES = {
    "GBPUSD": "London Breakout (primary) + EMA Hybrid",
    "EURUSD": "ICT/SMC + EMA Hybrid",
    "XAUUSD": "ICT/SMC + EMA Hybrid (highest volatility)",
    "AUDUSD": "EMA Hybrid",
    "USDJPY": "EMA Hybrid",
}


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="TradingAgents — Exness MT5 Forex Trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--symbol",  default="GBPUSD",
                   help="MT5 forex symbol (default: GBPUSD)")
    p.add_argument("--date",    default=date.today().isoformat(),
                   help="Analysis date YYYY-MM-DD (default: today)")

    # LLM
    p.add_argument("--provider",    default="deepseek", choices=list(PROVIDER_DEFAULTS))
    p.add_argument("--deep-model",  default=None)
    p.add_argument("--quick-model", default=None)
    p.add_argument("--no-llm-gate", action="store_true",
                   help="Skip LLM sentiment confirmation (use technical signal only)")

    # Execution
    p.add_argument("--execute",  action="store_true", help="Place real trades via MT5")
    p.add_argument("--dry-run",  action="store_true", help="Simulate without sending to MT5")

    # Risk
    p.add_argument("--balance",            type=float, default=100.0)
    p.add_argument("--risk-pct",           type=float, default=1.0,
                   help="Risk per trade %% (default 1%% — $1 on $100)")
    p.add_argument("--max-daily-loss-pct", type=float, default=3.0,
                   help="Daily loss limit %% (default 3%% = $3)")
    p.add_argument("--max-drawdown-pct",   type=float, default=15.0)
    p.add_argument("--max-positions",      type=int,   default=2)
    p.add_argument("--tp-rr",             type=float, default=2.0)

    # Filters
    p.add_argument("--no-session-filter", action="store_true")
    p.add_argument("--no-news-filter",    action="store_true")

    # MT5
    p.add_argument("--mt5-host",     default="localhost")
    p.add_argument("--mt5-port",     type=int, default=18812)
    p.add_argument("--mt5-login",    type=int, default=None)
    p.add_argument("--mt5-password", default=None)
    p.add_argument("--mt5-server",   default=None)

    return p.parse_args()


# ── Session check ─────────────────────────────────────────────────────────────

def check_session(symbol: str, skip: bool) -> bool:
    if skip:
        return True
    from tradingagents.broker.session_filter import is_tradeable, session_info
    allowed, reason = is_tradeable(symbol)
    print(f"\n  Session : {session_info()}")
    if not allowed:
        print(f"  Warning : {reason}")
    return allowed


def check_news(symbol: str, skip: bool) -> bool:
    if skip:
        return True
    from tradingagents.broker.news_calendar import NewsCalendar
    cal = NewsCalendar()
    blocked, reason = cal.is_news_window(symbol)
    if blocked:
        print(f"\n  NEWS BLOCK: {reason}")
        return False
    upcoming = cal.next_events(symbol, n=2)
    for ev in upcoming:
        lkt = ev["_utc"] + timedelta(hours=5, minutes=30)
        print(f"  Upcoming news: {ev['title']} ({ev['country']}) "
              f"— {lkt.strftime('%H:%M')} LKT")
    return True


# ── Technical strategy run ────────────────────────────────────────────────────

def run_technical_strategies(mt5_symbol: str):
    from tradingagents.broker.forex_strategy import run_all_strategies
    _header("Technical Strategy Analysis")
    print(f"  Pair     : {mt5_symbol}")
    print(f"  Profile  : {PAIR_PROFILES.get(mt5_symbol.upper(), 'All strategies')}")
    now_utc = datetime.now(timezone.utc)
    lkt = now_utc + timedelta(hours=5, minutes=30)
    print(f"  Time UTC : {now_utc.strftime('%H:%M')}  |  LKT: {lkt.strftime('%H:%M')}")
    _divider()
    print()

    signal = run_all_strategies(mt5_symbol)

    if signal is None:
        print("  Result: WAIT — no strategy produced an actionable signal right now.")
    else:
        action_icon = "🟢 BUY" if signal.action == "BUY" else "🔴 SELL"
        print(f"  Strategy   : {signal.strategy}")
        print(f"  Signal     : {action_icon}")
        print(f"  Confidence : {signal.confidence:.0%}")
        print(f"  Reason     : {signal.reason}")
        if signal.entry_price: print(f"  Entry      : {signal.entry_price:.5f}")
        if signal.stop_loss:   print(f"  Stop-loss  : {signal.stop_loss:.5f}")
        if signal.take_profit: print(f"  Take-profit: {signal.take_profit:.5f}")
        if signal.hard_exit_hour_utc:
            print(f"  Hard exit  : {signal.hard_exit_hour_utc:02d}:00 UTC "
                  f"({signal.hard_exit_hour_utc + 5}:30 LKT)")
    return signal


# ── LLM analysis (sentiment gate) ────────────────────────────────────────────

def run_llm_analysis(symbol_yf: str, mt5_symbol: str, trade_date: str, args):
    """
    Run TradingAgents multi-agent analysis.
    For forex: market analyst (technicals) + news analyst (macro sentiment).
    Returns (final_state, llm_signal).
    """
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    deep_model, quick_model = PROVIDER_DEFAULTS[args.provider]
    if args.deep_model:  deep_model  = args.deep_model
    if args.quick_model: quick_model = args.quick_model

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"]    = args.provider
    config["deep_think_llm"]  = deep_model
    config["quick_think_llm"] = quick_model
    config["checkpoint_enabled"] = True

    _header("LLM Sentiment Gate (Market + News Analysis)")
    print(f"  Symbol   : {symbol_yf}  (MT5: {mt5_symbol})")
    print(f"  Date     : {trade_date}")
    print(f"  Provider : {args.provider}  /  {deep_model}")
    print(f"  Analysts : market, news  (forex mode)")
    _divider()
    print("\nRunning LLM analysis… (2–4 minutes with DeepSeek)\n")

    ta = TradingAgentsGraph(
        selected_analysts=["market", "news"],
        debug=False,
        config=config,
    )
    final_state, llm_signal = ta.propagate(symbol_yf, trade_date)

    _header(f"LLM SIGNAL:  {llm_signal}")
    if final_state.get("final_trade_decision"):
        print("\n" + final_state["final_trade_decision"])

    return final_state, llm_signal


def llm_agrees(tech_signal_action: str, llm_signal: str) -> bool:
    """
    Returns True if the LLM direction agrees with the technical signal.
    BUY aligns with: Buy, Overweight
    SELL aligns with: Sell, Underweight
    """
    bull_signals = {"buy", "overweight"}
    bear_signals = {"sell", "underweight"}
    llm = llm_signal.lower()

    if tech_signal_action == "BUY"  and llm in bull_signals: return True
    if tech_signal_action == "SELL" and llm in bear_signals: return True
    return False


# ── Execution ─────────────────────────────────────────────────────────────────

def run_execution(tech_signal, mt5_symbol: str, final_state: dict, args):
    from tradingagents.broker.mt5_client    import MT5Client
    from tradingagents.broker.portfolio     import Portfolio
    from tradingagents.broker.position_sizer import PositionSizer
    from tradingagents.broker.risk_guard    import RiskGuard, RiskConfig
    from tradingagents.broker.executor      import TradeExecutor

    portfolio = Portfolio(
        os.path.join(os.path.expanduser("~"), ".tradingagents", "portfolio",
                     "forex_state.json")  # separate portfolio file for forex
    )
    portfolio.state.initial_balance = args.balance

    risk_cfg = RiskConfig(
        max_risk_per_trade_pct = args.risk_pct,
        max_daily_loss_pct     = args.max_daily_loss_pct,
        max_drawdown_pct       = args.max_drawdown_pct,
        max_open_positions     = args.max_positions,
    )

    # Use tech signal levels (more precise than LLM estimates)
    entry_price = tech_signal.entry_price
    stop_loss   = tech_signal.stop_loss

    # ── Dry run ───────────────────────────────────────────────────────────────
    if args.dry_run:
        _header("DRY RUN — no order sent")
        risk_amt = args.balance * args.risk_pct / 100
        print(f"  Symbol    : {mt5_symbol}")
        print(f"  Signal    : {tech_signal.action}")
        print(f"  Strategy  : {tech_signal.strategy}")
        print(f"  Balance   : ${args.balance:.2f}")
        print(f"  Risk/trade: {args.risk_pct}%  (${risk_amt:.2f} max loss)")
        if entry_price: print(f"  Entry     : {entry_price:.5f}")
        if stop_loss:   print(f"  Stop-loss : {stop_loss:.5f}")
        if tech_signal.take_profit: print(f"  Take-prof : {tech_signal.take_profit:.5f}")
        if tech_signal.hard_exit_hour_utc:
            print(f"  Hard exit : {tech_signal.hard_exit_hour_utc:02d}:00 UTC")
        _divider()
        return

    # ── Live ──────────────────────────────────────────────────────────────────
    _header("Connecting to MT5")
    mt5 = MT5Client(host=args.mt5_host, port=args.mt5_port)

    try:
        if not mt5.initialize(
            login=args.mt5_login,
            password=args.mt5_password,
            server=args.mt5_server,
        ):
            print("\n  ERROR: Cannot connect to MT5.")
            print("  • Open MT5 terminal and log in to Exness.")
            print("  • Linux: start mt5linux server → python -m mt5linux")
            print(f"  • Error: {mt5.last_error()}")
            sys.exit(1)

        acct = mt5.account_info()
        if acct:
            portfolio.sync_balance(acct.balance)
            print(f"\n  Account  : #{acct.login}")
            print(f"  Balance  : ${acct.balance:.2f} {acct.currency}")
            print(f"  Equity   : ${acct.equity:.2f}")
            print(f"  Leverage : 1:{acct.leverage}")
            _divider()

        mt5.symbol_select(mt5_symbol, True)

        executor = TradeExecutor(
            mt5, portfolio,
            RiskGuard(risk_cfg, portfolio),
            PositionSizer(mt5),
            take_profit_rr=args.tp_rr,
        )

        print(f"\nExecuting '{tech_signal.action}' on {mt5_symbol}  "
              f"[{tech_signal.strategy}] …\n")
        result = executor.execute_signal(
            symbol            = mt5_symbol,
            signal            = tech_signal.action,
            agent_entry_price = entry_price,
            agent_stop_loss   = stop_loss,
        )

        _header("RESULT")
        if result.success:
            print(f"  TRADE PLACED")
            print(f"  Ticket     : {result.ticket}")
            print(f"  Action     : {result.action}")
            print(f"  Volume     : {result.volume:.2f} lots")
            print(f"  Price      : {result.price:.5f}")
            print(f"  Stop-loss  : {result.stop_loss:.5f}")
            print(f"  Take-profit: {result.take_profit:.5f}")
            if tech_signal.hard_exit_hour_utc:
                print(f"\n  REMINDER: Force-close by "
                      f"{tech_signal.hard_exit_hour_utc:02d}:00 UTC "
                      f"({tech_signal.hard_exit_hour_utc + 5}:30 LKT)")
        else:
            print(f"  NOT PLACED")
            print(f"  Reason : {result.message}")
        _divider()

        print("\nPortfolio Summary")
        print("-" * 40)
        print(portfolio.summary())

    finally:
        mt5.shutdown()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _divider(): print("=" * 60)
def _header(t): print(); _divider(); print(f"  {t}"); _divider()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Normalise symbol (strip # for forex, uppercase)
    mt5_symbol = args.symbol.upper().strip().lstrip("#")
    from tradingagents.broker.symbol_mapper import to_yfinance_ticker
    symbol_yf  = to_yfinance_ticker(mt5_symbol)

    _header("TradingAgents FOREX Bot")
    print(f"  Symbol   : {mt5_symbol}  →  yfinance: {symbol_yf}")
    print(f"  Strategy : {PAIR_PROFILES.get(mt5_symbol, 'All strategies')}")
    _divider()

    logger.info("MT5 symbol: %s  |  yfinance: %s", mt5_symbol, symbol_yf)

    # Pre-trade filters
    if args.execute or args.dry_run:
        if not check_session(mt5_symbol, args.no_session_filter):
            print("\n  Trade skipped — outside active session.")
            print("  Forex best: London 08:00–17:00 UTC  |  NY 13:30–22:00 UTC")
            sys.exit(0)
        if not check_news(mt5_symbol, args.no_news_filter):
            print("\n  Trade skipped — high-impact news imminent.")
            sys.exit(0)

    # ── Step 1: Technical strategies ─────────────────────────────────────────
    tech_signal = run_technical_strategies(mt5_symbol)

    if tech_signal is None:
        print("\n  No technical signal at this time.")
        _print_schedule()
        sys.exit(0)

    print(f"\n  Technical signal: {tech_signal.action} "
          f"({tech_signal.strategy}, conf={tech_signal.confidence:.0%})")

    # ── Step 2: LLM gate ─────────────────────────────────────────────────────
    final_state  = {}
    llm_signal   = "Hold"

    if not args.no_llm_gate:
        final_state, llm_signal = run_llm_analysis(
            symbol_yf, mt5_symbol, args.date, args
        )
        agrees = llm_agrees(tech_signal.action, llm_signal)
        _header("Gate Decision")
        print(f"  Technical : {tech_signal.action}  ({tech_signal.strategy})")
        print(f"  LLM       : {llm_signal}")
        print(f"  Agreement : {'YES — proceed' if agrees else 'NO — SKIP'}")
        _divider()

        if not agrees:
            print(f"\n  Trade blocked: technical {tech_signal.action} vs LLM {llm_signal}.")
            print("  Wait for LLM agreement or run with --no-llm-gate to skip this check.")
            sys.exit(0)
    else:
        print("\n  LLM gate skipped (--no-llm-gate). Proceeding on technical signal only.")

    # ── Step 3: Execute ───────────────────────────────────────────────────────
    if args.execute or args.dry_run:
        run_execution(tech_signal, mt5_symbol, final_state, args)
    else:
        print(f"\n  Tip: add --execute to place the trade, --dry-run to preview.")
        print(f"  Example:  python run_forex.py --symbol {mt5_symbol} --execute\n")


def _print_schedule():
    print("\n  Optimal times (LKT = Sri Lanka Time):")
    print("  London Breakout : 12:30–14:30 LKT  (entry only)")
    print("  ICT London KZ   : 07:30–10:30 LKT")
    print("  ICT NY KZ       : 17:30–20:30 LKT")
    print("  EMA windows     : 12:30–16:30 LKT  or  18:30–21:30 LKT")


if __name__ == "__main__":
    main()
