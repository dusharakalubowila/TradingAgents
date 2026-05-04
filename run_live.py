#!/usr/bin/env python3
"""
TradingAgents Live Trading — Exness MT5 (US Stock CFDs)

Best symbols: #NVDA  #AAPL  #TSLA  #MSFT  #META  #AMD

QUICK START
-----------
  Analysis only (no trade):
    python run_live.py --symbol "#NVDA"

  Demo dry-run (see what would happen):
    python run_live.py --symbol "#NVDA" --execute --dry-run

  Live trade:
    python run_live.py --symbol "#NVDA" --execute

Sri Lanka trading window:
  US pre-market  → 15:30 – 19:00 LKT
  US regular     → 19:00 – 01:30 LKT  ← best time
  Close all by   → 01:30 LKT (before US close)

LINUX MT5 SETUP
---------------
  1. sudo apt install wine64 winetricks
  2. Install MT5 from Exness under Wine
  3. pip install mt5linux
  4. python -m mt5linux   (run in separate terminal)
"""

import argparse
import logging
import os
import re
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_live")

# ── Provider defaults ────────────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "deepseek":  ("deepseek-chat",         "deepseek-chat"),
    "openai":    ("gpt-4.1",               "gpt-4.1-mini"),
    "anthropic": ("claude-sonnet-4-6",     "claude-haiku-4-5-20251001"),
    "google":    ("gemini-2.5-pro",        "gemini-2.5-flash"),
    "ollama":    ("llama3.1:8b",           "llama3.1:8b"),
}

# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="TradingAgents — Exness MT5 US Stock CFD trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--symbol", default="#NVDA",
                   help="Exness stock CFD symbol (default: #NVDA)")
    p.add_argument("--date",   default=date.today().isoformat(),
                   help="Analysis date YYYY-MM-DD (default: today)")

    # LLM
    p.add_argument("--provider",     default="deepseek",
                   choices=list(PROVIDER_DEFAULTS),
                   help="LLM provider (default: deepseek)")
    p.add_argument("--deep-model",   default=None)
    p.add_argument("--quick-model",  default=None)

    # Execution
    p.add_argument("--execute",  action="store_true",
                   help="Place real trades via MT5")
    p.add_argument("--dry-run",  action="store_true",
                   help="Simulate trade without sending to MT5")

    # Risk
    p.add_argument("--balance",            type=float, default=100.0)
    p.add_argument("--risk-pct",           type=float, default=2.0,
                   help="Risk per trade %% (default 2%%)")
    p.add_argument("--max-daily-loss-pct", type=float, default=5.0)
    p.add_argument("--max-drawdown-pct",   type=float, default=20.0)
    p.add_argument("--max-positions",      type=int,   default=3)
    p.add_argument("--tp-rr",             type=float, default=2.0,
                   help="Take-profit reward:risk ratio (default 2.0)")

    # Filters
    p.add_argument("--no-session-filter", action="store_true",
                   help="Skip trading session check")
    p.add_argument("--no-news-filter",    action="store_true",
                   help="Skip high-impact news check")

    # MT5
    p.add_argument("--mt5-host",     default="localhost")
    p.add_argument("--mt5-port",     type=int, default=18812)
    p.add_argument("--mt5-login",    type=int, default=None)
    p.add_argument("--mt5-password", default=None)
    p.add_argument("--mt5-server",   default=None)

    return p.parse_args()


# ── Symbol helpers ───────────────────────────────────────────────────────────

def ensure_exness_stock_symbol(symbol: str) -> str:
    """Ensure stock CFDs have # prefix for Exness (e.g. NVDA → #NVDA)."""
    s = symbol.upper().strip()
    from tradingagents.broker.symbol_mapper import is_forex, is_crypto
    if is_forex(s) or is_crypto(s):
        return s
    if not s.startswith("#"):
        return "#" + s
    return s


def to_yfinance(mt5_symbol: str) -> str:
    """Convert Exness symbol to yfinance ticker."""
    from tradingagents.broker.symbol_mapper import to_yfinance_ticker
    return to_yfinance_ticker(mt5_symbol)


# ── Stop-loss extraction ─────────────────────────────────────────────────────

def _parse_price(text: str):
    """Extract first float from a string like '**Stop Loss**: 127.50'."""
    m = re.search(r"[\$]?\s*([\d,]+\.?\d*)", text.replace(",", ""))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def extract_trade_levels(final_state: dict):
    """
    Extract entry_price and stop_loss from the trader's structured output.
    Looks for '**Entry Price**:' and '**Stop Loss**:' markdown headers
    produced by render_trader_proposal().
    """
    entry_price = None
    stop_loss   = None
    plan = final_state.get("trader_investment_plan", "")

    for line in plan.split("\n"):
        ll = line.lower()
        if "**entry price**" in ll and entry_price is None:
            entry_price = _parse_price(line.split(":", 1)[-1])
        elif "**stop loss**" in ll and stop_loss is None:
            stop_loss = _parse_price(line.split(":", 1)[-1])
        # Fallback plain text
        elif "entry" in ll and "price" in ll and entry_price is None:
            entry_price = _parse_price(line.split(":", 1)[-1] if ":" in line else line)
        elif "stop" in ll and stop_loss is None:
            stop_loss = _parse_price(line.split(":", 1)[-1] if ":" in line else line)

    if entry_price:
        logger.info("Agent entry price: %.4f", entry_price)
    if stop_loss:
        logger.info("Agent stop loss:   %.4f", stop_loss)
    else:
        logger.info("No stop loss from agent — will auto-calculate from ATR/default.")

    return entry_price, stop_loss


# ── Pre-trade checks ─────────────────────────────────────────────────────────

def check_session(symbol: str, skip: bool) -> bool:
    """Returns True if trading is allowed right now."""
    if skip:
        return True
    from tradingagents.broker.session_filter import is_tradeable, session_info
    allowed, reason = is_tradeable(symbol)
    print(f"\n  Session: {session_info()}")
    if not allowed:
        print(f"  ⚠  {reason}")
    return allowed


def check_news(symbol: str, skip: bool) -> bool:
    """Returns True if no high-impact news is imminent."""
    if skip:
        return True
    from tradingagents.broker.news_calendar import NewsCalendar
    cal = NewsCalendar()
    blocked, reason = cal.is_news_window(symbol)
    if blocked:
        print(f"\n  ⚠  NEWS BLOCK: {reason}")
        return False
    upcoming = cal.next_events(symbol, n=2)
    if upcoming:
        for ev in upcoming:
            t = ev["_utc"]
            lkt = t + timedelta(hours=5, minutes=30)
            print(f"  📅 Upcoming: {ev['title']} ({ev['country']}) "
                  f"— {lkt.strftime('%H:%M')} LKT")
    return True


# ── Analysis ─────────────────────────────────────────────────────────────────

def run_analysis(symbol_yf: str, mt5_symbol: str, trade_date: str, args):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.broker.symbol_mapper import get_analysts_for_symbol

    deep_model, quick_model = PROVIDER_DEFAULTS.get(
        args.provider, ("deepseek-chat", "deepseek-chat")
    )
    if args.deep_model:  deep_model  = args.deep_model
    if args.quick_model: quick_model = args.quick_model

    analysts = get_analysts_for_symbol(mt5_symbol)  # all 4 for stocks

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"]    = args.provider
    config["deep_think_llm"]  = deep_model
    config["quick_think_llm"] = quick_model
    config["checkpoint_enabled"] = True

    _header("TradingAgents Analysis")
    print(f"  Symbol   : {symbol_yf}  (Exness: {mt5_symbol})")
    print(f"  Date     : {trade_date}")
    print(f"  Provider : {args.provider}  /  {deep_model}")
    print(f"  Analysts : {', '.join(analysts)}")
    _divider()
    print("\nRunning analysis… (3–8 minutes with DeepSeek)\n")

    ta = TradingAgentsGraph(
        selected_analysts=analysts,
        debug=False,
        config=config,
    )
    final_state, signal = ta.propagate(symbol_yf, trade_date)

    _header(f"DECISION:  {signal}")
    if final_state.get("final_trade_decision"):
        print("\n" + final_state["final_trade_decision"])

    return final_state, signal


# ── Execution ────────────────────────────────────────────────────────────────

def run_execution(signal: str, mt5_symbol: str, final_state: dict, args):
    from tradingagents.broker.mt5_client   import MT5Client
    from tradingagents.broker.portfolio    import Portfolio
    from tradingagents.broker.position_sizer import PositionSizer
    from tradingagents.broker.risk_guard   import RiskGuard, RiskConfig
    from tradingagents.broker.executor     import TradeExecutor

    portfolio = Portfolio(
        os.path.join(os.path.expanduser("~"), ".tradingagents", "portfolio", "state.json")
    )
    portfolio.state.initial_balance = args.balance

    risk_cfg = RiskConfig(
        max_risk_per_trade_pct = args.risk_pct,
        max_daily_loss_pct     = args.max_daily_loss_pct,
        max_drawdown_pct       = args.max_drawdown_pct,
        max_open_positions     = args.max_positions,
    )

    entry_price, stop_loss = extract_trade_levels(final_state)

    # ── Dry run ──────────────────────────────────────────────────────────────
    if args.dry_run:
        _header("DRY RUN — no order sent")
        risk_amt = args.balance * args.risk_pct / 100
        print(f"  Symbol    : {mt5_symbol}")
        print(f"  Signal    : {signal}")
        print(f"  Balance   : ${args.balance:.2f}")
        print(f"  Risk/trade: {args.risk_pct}%  (${risk_amt:.2f} max loss)")
        if entry_price: print(f"  Entry     : {entry_price:.4f}")
        if stop_loss:   print(f"  Stop-loss : {stop_loss:.4f}")
        _divider()
        return

    # ── Live ─────────────────────────────────────────────────────────────────
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
            print("  • Linux: start mt5linux server first  →  python -m mt5linux")
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

        print(f"\nExecuting signal  '{signal}'  on  {mt5_symbol} …\n")
        result = executor.execute_signal(
            symbol           = mt5_symbol,
            signal           = signal,
            agent_entry_price= entry_price,
            agent_stop_loss  = stop_loss,
        )

        _header("RESULT")
        if result.success:
            print(f"  ✅ TRADE PLACED")
            print(f"  Ticket     : {result.ticket}")
            print(f"  Action     : {result.action}")
            print(f"  Volume     : {result.volume:.2f} lots")
            print(f"  Price      : {result.price:.4f}")
            print(f"  Stop-loss  : {result.stop_loss:.4f}")
            print(f"  Take-profit: {result.take_profit:.4f}")
            print(f"\n  ⚠  REMEMBER: Close before 01:30 LKT (US market close)")
        else:
            print(f"  ❌ NOT PLACED")
            print(f"  Reason  : {result.message}")
        _divider()

        print("\nPortfolio Summary")
        print("-" * 40)
        print(portfolio.summary())

    finally:
        mt5.shutdown()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _divider(): print("=" * 60)
def _header(t): print(); _divider(); print(f"  {t}"); _divider()


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Normalise symbol
    mt5_symbol = ensure_exness_stock_symbol(args.symbol)
    symbol_yf  = to_yfinance(mt5_symbol)

    logger.info("Exness symbol: %s  |  yfinance: %s", mt5_symbol, symbol_yf)

    # Pre-trade filters (only relevant when executing)
    if args.execute or args.dry_run:
        if not check_session(mt5_symbol, args.no_session_filter):
            print("\n  Trade skipped — outside active session.")
            print("  Best time: 19:00 – 01:30 LKT  (US market hours)")
            sys.exit(0)

        if not check_news(mt5_symbol, args.no_news_filter):
            print("\n  Trade skipped — high-impact news imminent.")
            sys.exit(0)

    # Run analysis
    final_state, signal = run_analysis(symbol_yf, mt5_symbol, args.date, args)

    # Execute
    if args.execute or args.dry_run:
        run_execution(signal, mt5_symbol, final_state, args)
    else:
        print("\n  Tip: add --execute to place the trade, --dry-run to preview.")
        print(f"  Example:  python run_live.py --symbol \"{mt5_symbol}\" --execute\n")


if __name__ == "__main__":
    main()
