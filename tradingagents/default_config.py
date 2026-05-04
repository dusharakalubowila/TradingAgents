import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # ── Broker / live trading (Exness MT5) ────────────────────────────────────
    "broker": {
        # Portfolio state is persisted here across runs
        "portfolio_state_path": os.path.join(_TRADINGAGENTS_HOME, "portfolio", "state.json"),
        # Starting capital for risk calculations
        "initial_balance": 100.0,
        # Risk per trade as % of current balance (2% of $100 = $2)
        "risk_per_trade_pct": 2.0,
        # Daily loss limit: pause trading when day's loss exceeds this %
        "max_daily_loss_pct": 5.0,
        # Max drawdown: pause when balance drops this % from its peak
        "max_drawdown_pct": 20.0,
        # Maximum concurrent open positions
        "max_open_positions": 3,
        # "any" = all non-Hold signals trade; "strong" = only Buy / Sell
        "min_signal_strength": "any",
        # Take-profit reward:risk ratio (2.0 = 2× the stop distance)
        "take_profit_rr": 2.0,
        # MT5 / mt5linux connection (Linux only)
        "mt5_host": "localhost",
        "mt5_port": 18812,
        # Optional: set to your Exness account number / password / server
        # Leave None to use whatever the MT5 terminal is already logged in to
        "mt5_login": None,
        "mt5_password": None,
        "mt5_server": None,
        # Exness account-type suffix if your symbols use one (e.g. "m" → EURUSDm)
        "exness_suffix": "",
    },
}
