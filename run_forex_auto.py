#!/usr/bin/env python3
"""
TradingAgents Forex Automation Daemon

Runs 24/7 on your VPS. Automatically:
  - Checks all 3 strategies at every optimal window
  - Places trades when signal + LLM agree
  - Closes London Breakout positions at 12:00 UTC hard exit
  - Logs every decision to ~/.tradingagents/logs/forex_auto.log
  - Skips weekends automatically

Schedule (UTC):
  02:00  ICT London Kill Zone check   (EURUSD, GBPUSD)
  07:00  London Breakout entry        (GBPUSD)
  07:00  EMA window check             (EURUSD)
  12:00  HARD EXIT London Breakout positions
  12:00  ICT NY Kill Zone check       (EURUSD, XAUUSD)
  13:00  EMA window check             (EURUSD)

Usage:
  python run_forex_auto.py                   # start daemon
  python run_forex_auto.py --dry-run         # simulate (no real orders)
  python run_forex_auto.py --no-llm-gate     # skip LLM, tech only
  python run_forex_auto.py --once            # run once now and exit

Run in background on VPS:
  nohup python run_forex_auto.py >> ~/.tradingagents/logs/forex_auto.log 2>&1 &
  echo $! > ~/.tradingagents/forex_daemon.pid
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Logging setup ─────────────────────────────────────────────────────────────

LOG_DIR = Path(os.path.expanduser("~")) / ".tradingagents" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "forex_auto.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("forex_auto")

# ── Schedule definition ───────────────────────────────────────────────────────

# Each job: (utc_hour, utc_minute, label, pairs, use_llm_gate)
SCHEDULE = [
    # ICT London kill zone (02:00–05:00 UTC)
    (2,  0,  "ICT_LONDON_KZ",    ["EURUSD", "GBPUSD"], True),

    # London Breakout entry window opens (07:00–09:00 UTC)
    (7,  0,  "LONDON_BREAKOUT",  ["GBPUSD", "EURUSD"],  True),

    # EMA Hybrid — first window (07:00–11:00 UTC)
    (7,  30, "EMA_WINDOW_1",     ["EURUSD"],            True),

    # HARD EXIT: close all London Breakout positions
    (12, 0,  "HARD_EXIT_LB",     [],                    False),

    # ICT NY kill zone (12:00–15:00 UTC)
    (12, 5,  "ICT_NY_KZ",        ["EURUSD", "XAUUSD"],  True),

    # EMA Hybrid — second window (13:00–16:00 UTC) — fire at 13:05 so hour=13 when strategy runs
    (13, 5,  "EMA_WINDOW_2",     ["EURUSD", "GBPUSD"],  True),
]

# ── Provider defaults ─────────────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "deepseek":  ("deepseek-chat",      "deepseek-chat"),
    "openai":    ("gpt-4.1",            "gpt-4.1-mini"),
    "anthropic": ("claude-sonnet-4-6",  "claude-haiku-4-5-20251001"),
    "google":    ("gemini-2.5-pro",     "gemini-2.5-flash"),
    "ollama":    ("llama3.1:8b",        "llama3.1:8b"),
}


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="TradingAgents Forex Auto Daemon")
    p.add_argument("--dry-run",      action="store_true",
                   help="Simulate trades, no real orders placed")
    p.add_argument("--no-llm-gate",  action="store_true",
                   help="Skip LLM sentiment gate (faster, less accurate)")
    p.add_argument("--once",         action="store_true",
                   help="Run all strategy checks once now and exit")
    p.add_argument("--provider",     default="deepseek",
                   choices=list(PROVIDER_DEFAULTS))
    p.add_argument("--balance",      type=float, default=100.0)
    p.add_argument("--risk-pct",     type=float, default=1.0)
    p.add_argument("--max-daily-loss-pct", type=float, default=3.0)
    p.add_argument("--max-positions", type=int,  default=2)
    p.add_argument("--mt5-host",     default="localhost")
    p.add_argument("--mt5-port",     type=int,   default=18812)
    p.add_argument("--mt5-login",    type=int,   default=None)
    p.add_argument("--mt5-password", default=None)
    p.add_argument("--mt5-server",   default=None)
    return p.parse_args()


# ── Core logic ────────────────────────────────────────────────────────────────

def is_weekend(now: datetime) -> bool:
    """Saturday = 5, Sunday = 6 in Python weekday()."""
    return now.weekday() >= 5


def hard_close_london_breakout(args):
    """
    Force-close any open positions tagged as London Breakout at 12:00 UTC.
    Exness closes the whole position (no partial close needed at this stage).
    """
    logger.info("=== HARD EXIT: Closing all open London Breakout positions ===")

    if args.dry_run:
        logger.info("[DRY RUN] Would close London Breakout positions now.")
        return

    try:
        from tradingagents.broker.mt5_client import MT5Client
        mt5 = MT5Client(host=args.mt5_host, port=args.mt5_port)

        if not mt5.initialize(
            login=args.mt5_login,
            password=args.mt5_password,
            server=args.mt5_server,
        ):
            logger.error("Hard exit: MT5 connection failed — %s", mt5.last_error())
            return

        lb_pairs = ["GBPUSD", "EURUSD"]
        closed = 0
        try:
            for symbol in lb_pairs:
                positions = mt5.positions_get(symbol=symbol)
                for pos in positions:
                    # Close by sending reverse trade
                    order_type = 1 if pos.type == 0 else 0  # reverse direction
                    req = {
                        "action":   1,          # TRADE_ACTION_DEAL
                        "symbol":   symbol,
                        "volume":   pos.volume,
                        "type":     order_type,
                        "position": pos.ticket,
                        "comment":  "LB_hard_exit_12UTC",
                    }
                    result = mt5.order_send(req)
                    if result and result.retcode == 10009:
                        logger.info("Closed LB position ticket=%s %s %.2f lots @ %.5f",
                                    pos.ticket, symbol, pos.volume, result.price)
                        closed += 1
                    else:
                        logger.warning("Failed to close ticket=%s: %s",
                                       pos.ticket, getattr(result, 'comment', 'unknown'))
        finally:
            mt5.shutdown()

        logger.info("Hard exit complete. Closed %d position(s).", closed)

    except Exception as exc:
        logger.error("Hard exit error: %s", exc)


def run_strategy_for_pair(symbol: str, args, use_llm: bool, skip_session_filter: bool = False):
    """Run the full strategy pipeline for one pair."""
    logger.info("--- Analysing %s ---", symbol)

    try:
        from tradingagents.broker.forex_strategy import run_all_strategies
        from tradingagents.broker.symbol_mapper import to_yfinance_ticker
        from tradingagents.broker.news_calendar import NewsCalendar

        # Session filter removed — each strategy has its own time window check built in
        # (London Breakout: 07-09 UTC, ICT: kill zones, EMA: 07-11/13-16 UTC)

        # News check
        cal = NewsCalendar()
        blocked, news_reason = cal.is_news_window(symbol)
        if blocked:
            logger.warning("%s — news block: %s", symbol, news_reason)
            return

        # Technical strategies
        tech_signal = run_all_strategies(symbol)

        if tech_signal is None:
            logger.info("%s — no technical signal.", symbol)
            return

        logger.info("%s — tech signal: %s  strategy=%s  conf=%.0f%%",
                    symbol, tech_signal.action, tech_signal.strategy,
                    tech_signal.confidence * 100)

        # LLM gate
        if use_llm and not args.no_llm_gate:
            symbol_yf   = to_yfinance_ticker(symbol)
            trade_date  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            llm_signal  = _run_llm(symbol_yf, symbol, trade_date, args)
            agrees      = _llm_agrees(tech_signal.action, llm_signal)
            logger.info("%s — LLM: %s | agrees: %s", symbol, llm_signal, agrees)
            if not agrees:
                logger.info("%s — trade blocked by LLM gate.", symbol)
                return
        else:
            logger.info("%s — LLM gate skipped.", symbol)

        # Execute
        _execute(tech_signal, symbol, args)

    except Exception as exc:
        logger.error("Error analysing %s: %s", symbol, exc, exc_info=True)


def _run_llm(symbol_yf, mt5_symbol, trade_date, args):
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG

        deep_model, quick_model = PROVIDER_DEFAULTS[args.provider]
        config = DEFAULT_CONFIG.copy()
        config.update({
            "llm_provider":    args.provider,
            "deep_think_llm":  deep_model,
            "quick_think_llm": quick_model,
            "checkpoint_enabled": False,
        })
        ta = TradingAgentsGraph(selected_analysts=["market", "news"],
                                debug=False, config=config)
        # Use MT5 symbol (e.g. EURUSD) not yfinance ticker (EURUSD=X) —
        # the = sign fails the safe_ticker_component path validation
        _, llm_signal = ta.propagate(mt5_symbol, trade_date)
        return llm_signal
    except Exception as exc:
        logger.error("LLM analysis failed: %s", exc)
        return "Hold"


def _llm_agrees(tech_action: str, llm_signal: str) -> bool:
    bull = {"buy", "overweight"}
    bear = {"sell", "underweight"}
    llm  = llm_signal.lower()
    if tech_action == "BUY"  and llm in bull: return True
    if tech_action == "SELL" and llm in bear: return True
    return False


def _execute(tech_signal, mt5_symbol, args):
    if args.dry_run:
        logger.info("[DRY RUN] Would place %s on %s  entry=%.5f  sl=%.5f  tp=%.5f",
                    tech_signal.action, mt5_symbol,
                    tech_signal.entry_price or 0,
                    tech_signal.stop_loss   or 0,
                    tech_signal.take_profit or 0)
        return

    try:
        from tradingagents.broker.mt5_client     import MT5Client
        from tradingagents.broker.portfolio      import Portfolio
        from tradingagents.broker.position_sizer import PositionSizer
        from tradingagents.broker.risk_guard     import RiskGuard, RiskConfig
        from tradingagents.broker.executor       import TradeExecutor

        portfolio = Portfolio(
            os.path.join(os.path.expanduser("~"), ".tradingagents",
                         "portfolio", "forex_state.json")
        )
        portfolio.state.initial_balance = args.balance

        risk_cfg = RiskConfig(
            max_risk_per_trade_pct = args.risk_pct,
            max_daily_loss_pct     = args.max_daily_loss_pct,
            max_open_positions     = args.max_positions,
        )

        mt5 = None
        for attempt in range(1, 4):
            _mt5 = MT5Client(host=args.mt5_host, port=args.mt5_port)
            if _mt5.initialize(login=args.mt5_login, password=args.mt5_password,
                               server=args.mt5_server):
                mt5 = _mt5
                break
            logger.warning("MT5 connect attempt %d/3 failed: %s", attempt, _mt5.last_error())
            time.sleep(15)
        if mt5 is None:
            logger.error("MT5 connection failed after 3 attempts.")
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
                signal            = tech_signal.action,
                agent_entry_price = tech_signal.entry_price,
                agent_stop_loss   = tech_signal.stop_loss,
            )

            if result.success:
                logger.info("TRADE PLACED — ticket=%s  %s %s  %.2f lots  "
                            "price=%.5f  sl=%.5f  tp=%.5f",
                            result.ticket, tech_signal.action, mt5_symbol,
                            result.volume, result.price,
                            result.stop_loss, result.take_profit)
            else:
                logger.warning("Trade NOT placed on %s: %s", mt5_symbol, result.message)
        finally:
            mt5.shutdown()

    except Exception as exc:
        logger.error("Execution error on %s: %s", mt5_symbol, exc, exc_info=True)


# ── Scheduler ─────────────────────────────────────────────────────────────────

def run_job(job: tuple, args):
    """Execute a single scheduled job."""
    _, _, label, pairs, use_llm = job
    logger.info("==== JOB: %s ====", label)

    if label == "HARD_EXIT_LB":
        hard_close_london_breakout(args)
        return

    ict_job = "ICT" in label
    for symbol in pairs:
        run_strategy_for_pair(symbol, args, use_llm, skip_session_filter=ict_job)


def seconds_until(hour: int, minute: int, now: datetime) -> float:
    """Seconds from now until the next occurrence of hour:minute UTC."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main():
    args = parse_args()

    # Load .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Fill MT5 creds from environment if not passed via CLI
    if args.mt5_login    is None: args.mt5_login    = int(os.getenv("MT5_LOGIN", 0)) or None
    if args.mt5_password is None: args.mt5_password = os.getenv("MT5_PASSWORD")
    if args.mt5_server   is None: args.mt5_server   = os.getenv("MT5_SERVER")

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    logger.info("============================================================")
    logger.info(" TradingAgents Forex Auto Daemon  |  mode=%s", mode)
    logger.info(" Provider : %s", args.provider)
    logger.info(" Balance  : $%.2f  |  Risk: %.1f%%", args.balance, args.risk_pct)
    logger.info(" Log file : %s", LOG_FILE)
    logger.info("============================================================")

    # ── One-shot mode ─────────────────────────────────────────────────────────
    if args.once:
        logger.info("One-shot mode — running all strategy checks now.")
        now = datetime.now(timezone.utc)
        if is_weekend(now):
            logger.info("Weekend — forex market closed. Nothing to do.")
            return
        all_pairs = list(dict.fromkeys(
            p for _, _, _, pairs, _ in SCHEDULE for p in pairs
        ))
        for symbol in all_pairs:
            run_strategy_for_pair(symbol, args, use_llm=not args.no_llm_gate)
        return

    # ── Daemon loop ───────────────────────────────────────────────────────────
    logger.info("Daemon started. Waiting for scheduled windows...")
    logger.info("Schedule (UTC):")
    for h, m, label, pairs, _ in SCHEDULE:
        pairs_str = ", ".join(pairs) if pairs else "—"
        logger.info("  %02d:%02d  %-20s  %s", h, m, label, pairs_str)

    # Track which jobs have already fired today (avoid double-firing)
    fired_today: set = set()
    last_date = None

    while True:
        now = datetime.now(timezone.utc)

        # Reset fired list at midnight UTC
        if last_date != now.date():
            fired_today.clear()
            last_date = now.date()
            logger.info("--- New trading day: %s ---", now.date())

        if is_weekend(now):
            # Sleep until Monday 00:00 UTC
            monday = now + timedelta(days=(7 - now.weekday()))
            monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
            wait = (monday - now).total_seconds()
            logger.info("Weekend — market closed. Sleeping until Monday %s UTC.",
                        monday.strftime("%Y-%m-%d %H:%M"))
            time.sleep(min(wait, 3600))
            continue

        # Check each scheduled job
        for job in SCHEDULE:
            h, m, label, pairs, use_llm = job
            job_key = f"{now.date()}_{label}"

            if job_key in fired_today:
                continue

            # Fire if we're within 2 minutes of the scheduled time
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            diff   = abs((now - target).total_seconds())

            if diff <= 120:
                fired_today.add(job_key)
                run_job(job, args)

        # Sleep 60 seconds between checks
        time.sleep(60)


if __name__ == "__main__":
    main()
