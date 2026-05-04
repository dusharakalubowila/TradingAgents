#!/usr/bin/env python3
"""
TradingAgents live trading runner — Exness/MT5.

QUICK START
-----------
1. Analysis only (no trade placed):
       python run_live.py --symbol EURUSD --provider openai

2. Analysis + execute trade:
       python run_live.py --symbol EURUSD --provider openai --execute

3. Simulate execution without sending to MT5:
       python run_live.py --symbol EURUSD --provider openai --execute --dry-run

4. Crypto:
       python run_live.py --symbol BTCUSD --provider openai --execute

5. Stock CFD on Exness:
       python run_live.py --symbol "#AAPL" --provider openai --execute


LINUX MT5 SETUP (required for --execute on Linux)
--------------------------------------------------
  1. Install Wine:
         sudo apt install wine64 winetricks

  2. Download MT5 from your Exness account and install it:
         wine mt5setup.exe

  3. Open MT5 under Wine, log in to your Exness account.

  4. Install mt5linux:
         pip install mt5linux

  5. In a separate terminal, start the mt5linux bridge server:
         python -m mt5linux

  6. Now run this script with --execute.


ENVIRONMENT VARIABLES
---------------------
  OPENAI_API_KEY       (for --provider openai)
  ANTHROPIC_API_KEY    (for --provider anthropic)
  GOOGLE_API_KEY       (for --provider google)
  DEEPSEEK_API_KEY     (for --provider deepseek)
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_live")

# ──────────────────────────────────────────────────────────────────────────────
# Default models per provider
# ──────────────────────────────────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "openai":    ("gpt-4.1",              "gpt-4.1-mini"),
    "anthropic": ("claude-sonnet-4-6",    "claude-haiku-4-5-20251001"),
    "google":    ("gemini-2.5-pro",       "gemini-2.5-flash"),
    "deepseek":  ("deepseek-chat",        "deepseek-chat"),
    "ollama":    ("llama3.1:70b",         "llama3.1:8b"),
}


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="TradingAgents live trading — Exness/MT5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Target
    p.add_argument("--symbol", required=True,
                   help="MT5 symbol to trade (e.g. EURUSD, BTCUSD, #AAPL)")
    p.add_argument("--date", default=date.today().isoformat(),
                   help="Analysis date YYYY-MM-DD (default: today)")

    # LLM
    p.add_argument("--provider", default="openai",
                   choices=list(PROVIDER_DEFAULTS),
                   help="LLM provider (default: openai)")
    p.add_argument("--deep-model", default=None,
                   help="Deep-think model override")
    p.add_argument("--quick-model", default=None,
                   help="Quick-think model override")
    p.add_argument("--analysts", nargs="+",
                   default=["market", "news"],
                   choices=["market", "social", "news", "fundamentals"],
                   help="Analyst types to run (default: market news)")

    # Execution
    p.add_argument("--execute", action="store_true",
                   help="Place trades via MT5 (default: analysis only)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be traded without sending orders")

    # Risk / money management
    p.add_argument("--balance", type=float, default=100.0,
                   help="Starting balance for tracking (default: $100)")
    p.add_argument("--risk-pct", type=float, default=2.0,
                   help="Risk per trade as %% of balance (default: 2%%)")
    p.add_argument("--max-daily-loss-pct", type=float, default=5.0,
                   help="Daily loss limit in %% (default: 5%%)")
    p.add_argument("--max-drawdown-pct", type=float, default=20.0,
                   help="Max drawdown in %% before trading pauses (default: 20%%)")
    p.add_argument("--max-positions", type=int, default=3,
                   help="Max concurrent open positions (default: 3)")
    p.add_argument("--signal-strength", default="any",
                   choices=["any", "strong"],
                   help="'strong'=only Buy/Sell trade; 'any'=all non-Hold (default: any)")
    p.add_argument("--tp-rr", type=float, default=2.0,
                   help="Take-profit reward:risk ratio (default: 2.0)")

    # MT5 connection
    p.add_argument("--mt5-host", default="localhost",
                   help="mt5linux host (Linux only, default: localhost)")
    p.add_argument("--mt5-port", type=int, default=18812,
                   help="mt5linux port (Linux only, default: 18812)")
    p.add_argument("--mt5-login", type=int, default=None,
                   help="MT5 account number (optional, uses terminal login if omitted)")
    p.add_argument("--mt5-password", default=None,
                   help="MT5 account password")
    p.add_argument("--mt5-server", default=None,
                   help="MT5 server name (e.g. Exness-MT5Real)")
    p.add_argument("--exness-suffix", default="",
                   help="Symbol suffix for your account type (e.g. 'm' → EURUSDm)")

    return p.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Analysis
# ──────────────────────────────────────────────────────────────────────────────

def run_analysis(symbol_yf: str, mt5_symbol: str, trade_date: str, args):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    deep_model, quick_model = PROVIDER_DEFAULTS.get(args.provider, ("gpt-4.1", "gpt-4.1-mini"))
    if args.deep_model:
        deep_model = args.deep_model
    if args.quick_model:
        quick_model = args.quick_model

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = args.provider
    config["deep_think_llm"] = deep_model
    config["quick_think_llm"] = quick_model
    config["checkpoint_enabled"] = True

    _header("TradingAgents Analysis")
    print(f"  Symbol   : {symbol_yf}  (MT5: {mt5_symbol})")
    print(f"  Date     : {trade_date}")
    print(f"  Provider : {args.provider}  /  {deep_model}")
    print(f"  Analysts : {', '.join(args.analysts)}")
    _divider()

    ta = TradingAgentsGraph(
        selected_analysts=args.analysts,
        debug=False,
        config=config,
    )

    print("\nRunning analysis… (2–10 minutes depending on model)\n")
    final_state, signal = ta.propagate(symbol_yf, trade_date)

    _header(f"DECISION:  {signal}")
    if final_state.get("final_trade_decision"):
        print("\n" + final_state["final_trade_decision"])

    return final_state, signal


# ──────────────────────────────────────────────────────────────────────────────
# Trade level extraction
# ──────────────────────────────────────────────────────────────────────────────

def _parse_price_line(line: str):
    """Try to parse a float from a 'Key: value' line."""
    if ":" in line:
        try:
            return float(line.split(":")[-1].strip().replace(",", ""))
        except ValueError:
            pass
    return None


def extract_trade_levels(final_state: dict):
    """Extract entry price and stop-loss from the Trader's proposal."""
    entry_price = None
    stop_loss = None
    trader_plan = final_state.get("trader_investment_plan", "")

    for line in trader_plan.split("\n"):
        ll = line.lower()
        if ("entry price" in ll or "entry:" in ll) and entry_price is None:
            entry_price = _parse_price_line(line)
        if ("stop loss" in ll or "stop:" in ll) and stop_loss is None:
            stop_loss = _parse_price_line(line)

    return entry_price, stop_loss


# ──────────────────────────────────────────────────────────────────────────────
# Execution
# ──────────────────────────────────────────────────────────────────────────────

def run_execution(signal: str, mt5_symbol: str, final_state: dict, args):
    from tradingagents.broker.mt5_client import MT5Client
    from tradingagents.broker.portfolio import Portfolio
    from tradingagents.broker.position_sizer import PositionSizer
    from tradingagents.broker.risk_guard import RiskGuard, RiskConfig
    from tradingagents.broker.executor import TradeExecutor

    portfolio_path = os.path.join(
        os.path.expanduser("~"), ".tradingagents", "portfolio", "state.json"
    )
    portfolio = Portfolio(portfolio_path)
    portfolio.state.initial_balance = args.balance

    risk_cfg = RiskConfig(
        max_risk_per_trade_pct=args.risk_pct,
        max_daily_loss_pct=args.max_daily_loss_pct,
        max_drawdown_pct=args.max_drawdown_pct,
        max_open_positions=args.max_positions,
        min_signal_strength=args.signal_strength,
    )

    entry_price, stop_loss = extract_trade_levels(final_state)

    # ── Dry run ──────────────────────────────────────────────────────────────
    if args.dry_run:
        _header("DRY RUN — no order sent")
        print(f"  Symbol   : {mt5_symbol}")
        print(f"  Signal   : {signal}")
        print(f"  Balance  : ${args.balance:.2f}")
        print(f"  Risk/trade: {args.risk_pct}%  (${args.balance * args.risk_pct / 100:.2f})")
        if entry_price:
            print(f"  Entry    : {entry_price}")
        if stop_loss:
            print(f"  Stop-loss: {stop_loss}")
        _divider()
        return

    # ── Live execution ────────────────────────────────────────────────────────
    _header("Connecting to MT5")
    mt5 = MT5Client(host=args.mt5_host, port=args.mt5_port)

    try:
        if not mt5.initialize(
            login=args.mt5_login,
            password=args.mt5_password,
            server=args.mt5_server,
        ):
            print("\nERROR: Could not connect to MT5.")
            print("  • Make sure the MT5 terminal is open and logged in.")
            print("  • On Linux: start the mt5linux server first (python -m mt5linux).")
            print(f"  • Last error: {mt5.last_error()}")
            sys.exit(1)

        account = mt5.account_info()
        if account:
            portfolio.sync_balance(account.balance)
            print(f"\n  Account  : #{account.login}")
            print(f"  Balance  : ${account.balance:.2f} {account.currency}")
            print(f"  Equity   : ${account.equity:.2f}")
            print(f"  Leverage : 1:{account.leverage}")
            _divider()

        # Make sure symbol is visible in MarketWatch
        mt5.symbol_select(mt5_symbol, True)

        risk_guard = RiskGuard(risk_cfg, portfolio)
        sizer = PositionSizer(mt5)
        executor = TradeExecutor(
            mt5, portfolio, risk_guard, sizer,
            take_profit_rr=args.tp_rr,
        )

        print(f"\nExecuting signal  '{signal}'  on  {mt5_symbol} …\n")
        result = executor.execute_signal(
            symbol=mt5_symbol,
            signal=signal,
            agent_entry_price=entry_price,
            agent_stop_loss=stop_loss,
        )

        _header("TRADE RESULT")
        if result.success:
            print(f"  Status   : PLACED")
            print(f"  Ticket   : {result.ticket}")
            print(f"  Action   : {result.action}")
            print(f"  Volume   : {result.volume:.2f} lots")
            print(f"  Price    : {result.price:.5f}")
            print(f"  Stop-loss: {result.stop_loss:.5f}")
            print(f"  Take-profit: {result.take_profit:.5f}")
        else:
            print(f"  Status   : NOT PLACED")
            print(f"  Reason   : {result.message}")
        _divider()

        print("\nPortfolio Summary")
        print("-" * 40)
        print(portfolio.summary())

    finally:
        mt5.shutdown()


# ──────────────────────────────────────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────────────────────────────────────

def _divider():
    print("=" * 60)

def _header(title: str):
    print()
    _divider()
    print(f"  {title}")
    _divider()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    from tradingagents.broker.symbol_mapper import to_yfinance_ticker, to_mt5_symbol
    mt5_symbol = to_mt5_symbol(args.symbol, args.exness_suffix)
    symbol_yf = to_yfinance_ticker(mt5_symbol)

    logger.info("MT5 symbol: %s  |  yfinance ticker: %s", mt5_symbol, symbol_yf)

    final_state, signal = run_analysis(symbol_yf, mt5_symbol, args.date, args)

    if args.execute or args.dry_run:
        run_execution(signal, mt5_symbol, final_state, args)
    else:
        print("\nTip: add --execute to place the trade, or --dry-run to preview it.")
        print(f"Example:  python run_live.py --symbol {mt5_symbol} --execute\n")


if __name__ == "__main__":
    main()
