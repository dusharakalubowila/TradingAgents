import os

# Load .env file if it exists (picks up DEEPSEEK_API_KEY etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars must be set manually

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    "memory_log_max_entries": None,

    # ── LLM settings (DeepSeek default — cheap & high quality) ──────────────
    "llm_provider":   "deepseek",
    "deep_think_llm": "deepseek-chat",    # DeepSeek V3 — deep analysis
    "quick_think_llm":"deepseek-chat",    # same model, cheap enough
    "backend_url": None,

    # Provider-specific thinking configuration
    "google_thinking_level":  None,
    "openai_reasoning_effort": None,
    "anthropic_effort":        None,

    # Checkpoint/resume
    "checkpoint_enabled": False,

    # Output language
    "output_language": "English",

    # Debate settings
    "max_debate_rounds":      1,
    "max_risk_discuss_rounds":1,
    "max_recur_limit":        100,

    # Data vendors
    "data_vendors": {
        "core_stock_apis":    "yfinance",
        "technical_indicators":"yfinance",
        "fundamental_data":   "yfinance",
        "news_data":          "yfinance",
    },
    "tool_vendors": {},

    # ── Broker / live trading (Exness MT5) ───────────────────────────────────
    "broker": {
        "portfolio_state_path": os.path.join(_TRADINGAGENTS_HOME, "portfolio", "state.json"),
        "initial_balance":       100.0,
        "risk_per_trade_pct":    2.0,      # 2% = $2 per trade at $100
        "max_daily_loss_pct":    5.0,      # stop if down $5 in a day
        "max_drawdown_pct":      20.0,     # pause if down 20% from peak
        "max_open_positions":    3,
        "min_signal_strength":   "any",    # "any" or "strong"
        "take_profit_rr":        2.0,      # 2:1 reward/risk ratio
        "mt5_host":              "localhost",
        "mt5_port":              18812,
        "mt5_login":             None,
        "mt5_password":          None,
        "mt5_server":            None,
        "exness_suffix":         "",       # e.g. "" for Standard, "c" for Cent
        # Session filter: only trade during active market hours
        "session_filter":        True,
        # News filter: skip trades 30 min before high-impact events
        "news_filter":           True,
        "news_buffer_minutes":   30,
        # Intraday mode: automatically close all positions before market closes
        "intraday_only":         True,
    },
}
