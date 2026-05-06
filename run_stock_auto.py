#!/usr/bin/env python3
"""
TradingAgents Stock CFD Auto-Trading Daemon

Runs 24/7 on VPS. Wakes up during US market hours and analyses top
stock CFDs using the full 4-analyst LLM pipeline.

Schedule (UTC, Mon–Fri only):
  14:30  US market open  — analyse #NVDA, #TSLA
  17:00  Mid-session     — analyse #AAPL, #MSFT
  20:30  Pre-close       — close ALL open stock positions

Symbols traded on Exness: #NVDA  #TSLA  #AAPL  #MSFT
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG_DIR = Path(os.path.expanduser("~")) / ".tradingagents" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "stock_auto.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("stock_auto")

# Stock CFDs traded on Exness (# prefix required)
STOCKS = {
    "open":  ["#NVDA", "#TSLA"],
    "mid":   ["#AAPL", "#MSFT"],
}

# Schedule: (utc_hour, utc_minute, label, symbols_key_or_None)
SCHEDULE = [
    (14, 30, "OPEN_SESSION",  "open"),   # US market open
    (17,  0, "MID_SESSION",   "mid"),    # Mid-session check
    (20, 30, "CLOSE_ALL",      None),    # Force-close before US close
]

PROVIDER_DEFAULTS = {
    "deepseek":  ("deepseek-chat",      "deepseek-chat"),
    "openai":    ("gpt-4.1",            "gpt-4.1-mini"),
    "anthropic": ("claude-sonnet-4-6",  "claude-haiku-4-5-20251001"),
}


def parse_args():
    p = argparse.ArgumentParser(description="TradingAgents Stock CFD Auto Daemon")
    p.add_argument("--dry-run",  action="store_true", help="Simulate, no real orders")
    p.add_argument("--once",     action="store_true", help="Run all windows once and exit")
    p.add_argument("--provider", default="deepseek", choices=list(PROVIDER_DEFAULTS))
    p.add_argument("--balance",  type=float, default=100.0)
    p.add_argument("--risk-pct", type=float, default=2.0)
    p.add_argument("--max-daily-loss-pct", type=float, default=5.0)
    p.add_argument("--max-positions",      type=int,   default=3)
    p.add_argument("--mt5-host",     default="localhost")
    p.add_argument("--mt5-port",     type=int, default=18812)
    p.add_argument("--mt5-login",    type=int, default=None)
    p.add_argument("--mt5-password", default=None)
    p.add_argument("--mt5-server",   default=None)
    return p.parse_args()


def is_weekend(now: datetime) -> bool:
    return now.weekday() >= 5


def _mt5_connect(args):
    from tradingagents.broker.mt5_client import MT5Client
    mt5 = MT5Client(host=args.mt5_host, port=args.mt5_port)
    if not mt5.initialize(
        login=args.mt5_login,
        password=args.mt5_password,
        server=args.mt5_server,
    ):
        logger.error("MT5 connect failed: %s", mt5.last_error())
        return None
    return mt5


def close_all_stock_positions(args):
    """Close all open stock CFD positions — called at 20:30 UTC daily."""
    logger.info("=== CLOSE ALL: Closing all open stock positions ===")

    if args.dry_run:
        logger.info("[DRY RUN] Would close all stock positions now.")
        return

    mt5 = _mt5_connect(args)
    if mt5 is None:
        return

    try:
        all_positions = mt5.positions_get()
        if not all_positions:
            logger.info("No open positions to close.")
            return

        closed = 0
        for pos in all_positions:
            if not pos.symbol.startswith("#"):
                continue  # skip forex positions
            order_type = 1 if pos.type == 0 else 0
            req = {
                "action":   1,
                "symbol":   pos.symbol,
                "volume":   pos.volume,
                "type":     order_type,
                "position": pos.ticket,
                "comment":  "stock_close_20:30UTC",
            }
            result = mt5.order_send(req)
            if result and result.retcode == 10009:
                logger.info("Closed #%s  %s  %.2f lots @ %.4f",
                            pos.ticket, pos.symbol, pos.volume, result.price)
                closed += 1
            else:
                logger.warning("Failed to close #%s %s: %s",
                               pos.ticket, pos.symbol,
                               getattr(result, "comment", "unknown"))

        logger.info("Close-all complete. Closed %d stock position(s).", closed)
    finally:
        mt5.shutdown()


def analyse_and_trade(mt5_symbol: str, args):
    """Run full 4-analyst LLM pipeline for one stock and execute if signal found."""
    from tradingagents.broker.symbol_mapper import to_yfinance_ticker
    from tradingagents.broker.news_calendar import NewsCalendar

    logger.info("--- Analysing %s ---", mt5_symbol)

    # News block check
    try:
        cal = NewsCalendar()
        blocked, reason = cal.is_news_window(mt5_symbol)
        if blocked:
            logger.warning("%s — news block: %s", mt5_symbol, reason)
            return
    except Exception:
        pass

    # LLM analysis — all 4 analysts for stocks
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG

        deep_model, quick_model = PROVIDER_DEFAULTS[args.provider]
        config = DEFAULT_CONFIG.copy()
        config.update({
            "llm_provider":       args.provider,
            "deep_think_llm":     deep_model,
            "quick_think_llm":    quick_model,
            "checkpoint_enabled": True,
        })

        symbol_yf  = to_yfinance_ticker(mt5_symbol)
        trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        logger.info("%s — running 4-analyst LLM (3–8 min)…", mt5_symbol)
        ta = TradingAgentsGraph(
            selected_analysts=["market", "news", "fundamentals", "social_media"],
            debug=False,
            config=config,
        )
        final_state, signal = ta.propagate(symbol_yf, trade_date)
        logger.info("%s — LLM signal: %s", mt5_symbol, signal)

    except Exception as exc:
        logger.error("%s — LLM failed: %s", mt5_symbol, exc, exc_info=True)
        return

    if signal.lower() not in {"buy", "sell"}:
        logger.info("%s — signal is '%s', skipping.", mt5_symbol, signal)
        return

    # Extract stop-loss from agent output
    import re
    stop_loss = None
    plan = final_state.get("trader_investment_plan", "")
    for line in plan.split("\n"):
        if "stop" in line.lower():
            m = re.search(r"[\$]?\s*([\d,]+\.?\d*)", line.replace(",", ""))
            if m:
                try:
                    stop_loss = float(m.group(1))
                    break
                except ValueError:
                    pass

    # Execute
    if args.dry_run:
        logger.info("[DRY RUN] Would place %s on %s  sl=%s",
                    signal.upper(), mt5_symbol, stop_loss)
        return

    try:
        from tradingagents.broker.portfolio      import Portfolio
        from tradingagents.broker.position_sizer import PositionSizer
        from tradingagents.broker.risk_guard     import RiskGuard, RiskConfig
        from tradingagents.broker.executor       import TradeExecutor

        portfolio = Portfolio(
            os.path.join(os.path.expanduser("~"), ".tradingagents",
                         "portfolio", "stock_state.json")
        )
        portfolio.state.initial_balance = args.balance

        risk_cfg = RiskConfig(
            max_risk_per_trade_pct = args.risk_pct,
            max_daily_loss_pct     = args.max_daily_loss_pct,
            max_open_positions     = args.max_positions,
        )

        mt5 = _mt5_connect(args)
        if mt5 is None:
            return

        try:
            acct = mt5.account_info()
            if acct:
                portfolio.sync_balance(acct.balance)

            mt5.symbol_select(mt5_symbol, True)
            executor = TradeExecutor(
                mt5, portfolio,
                RiskGuard(risk_cfg, portfolio),
                PositionSizer(mt5),
                take_profit_rr=2.0,
            )
            result = executor.execute_signal(
                symbol            = mt5_symbol,
                signal            = signal.upper(),
                agent_entry_price = None,
                agent_stop_loss   = stop_loss,
            )

            if result.success:
                logger.info("TRADE PLACED — ticket=%s  %s %s  %.2f lots  "
                            "price=%.4f  sl=%.4f  tp=%.4f",
                            result.ticket, signal.upper(), mt5_symbol,
                            result.volume, result.price,
                            result.stop_loss, result.take_profit)
            else:
                logger.warning("Trade NOT placed on %s: %s",
                               mt5_symbol, result.message)
        finally:
            mt5.shutdown()

    except Exception as exc:
        logger.error("Execution error on %s: %s", mt5_symbol, exc, exc_info=True)


def run_job(label: str, symbols_key, args):
    logger.info("==== JOB: %s ====", label)

    if label == "CLOSE_ALL":
        close_all_stock_positions(args)
        return

    symbols = STOCKS.get(symbols_key, [])
    for sym in symbols:
        analyse_and_trade(sym, args)


def seconds_until(hour: int, minute: int, now: datetime) -> float:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main():
    args = parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if args.mt5_login    is None: args.mt5_login    = int(os.getenv("MT5_LOGIN", 0)) or None
    if args.mt5_password is None: args.mt5_password = os.getenv("MT5_PASSWORD")
    if args.mt5_server   is None: args.mt5_server   = os.getenv("MT5_SERVER")

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    logger.info("============================================================")
    logger.info(" TradingAgents Stock Auto Daemon  |  mode=%s", mode)
    logger.info(" Provider : %s", args.provider)
    logger.info(" Balance  : $%.2f  |  Risk: %.1f%%", args.balance, args.risk_pct)
    logger.info(" Log file : %s", LOG_FILE)
    logger.info("============================================================")

    if args.once:
        logger.info("One-shot mode — running all windows now.")
        for _, _, label, symbols_key in SCHEDULE:
            run_job(label, symbols_key, args)
        return

    now = datetime.now(timezone.utc)
    logger.info("Daemon started. Waiting for US market hours (UTC):")
    for h, m, label, key in SCHEDULE:
        syms = ", ".join(STOCKS.get(key, [])) if key else "—"
        logger.info("  %02d:%02d  %-16s  %s", h, m, label, syms)
    logger.info("--- New trading day: %s ---", now.strftime("%Y-%m-%d"))

    fired_today: set = set()
    last_day = now.date()

    while True:
        now = datetime.now(timezone.utc)

        if now.date() != last_day:
            fired_today.clear()
            last_day = now.date()
            logger.info("--- New trading day: %s ---", now.strftime("%Y-%m-%d"))

        if is_weekend(now):
            wait = seconds_until(0, 5, now)
            logger.info("Weekend — sleeping %.0f min.", wait / 60)
            time.sleep(wait)
            continue

        for job in SCHEDULE:
            h, m, label, symbols_key = job
            key = f"{label}_{now.date()}"
            if key in fired_today:
                continue
            secs = seconds_until(h, m, now)
            if 0 <= secs < 60:
                fired_today.add(key)
                run_job(label, symbols_key, args)
                break

        time.sleep(30)


if __name__ == "__main__":
    main()
