"""
Maps between MT5/Exness symbol names and yfinance tickers.

MT5 symbol   →   yfinance ticker (for analysis data)
  EURUSD     →   EURUSD=X
  EURUSDm    →   EURUSD=X
  BTCUSD     →   BTC-USD
  #AAPL      →   AAPL
  AAPL       →   AAPL
"""

_FOREX = {
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF",
    "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "EURAUD", "EURCHF",
    "AUDJPY", "CADJPY", "GBPAUD", "GBPCAD", "CHFJPY", "EURSGD",
    "XAUUSD", "XAGUSD",                             # metals as forex pairs
}

_CRYPTO = {
    "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "BNBUSD", "SOLUSD",
    "ADAUSD", "DOTUSD", "DOGEUSD", "LINKUSD", "MATICUSD",
}


def _strip_suffix(symbol: str) -> str:
    """Remove Exness account-type suffixes (m, c, pro, .exness, etc.)."""
    s = symbol.upper()
    for suffix in (".EXNESS", "M", "C"):
        if s.endswith(suffix) and len(s) > len(suffix) + 3:
            s = s[: -len(suffix)]
            break
    return s


def to_yfinance_ticker(mt5_symbol: str) -> str:
    """Convert an MT5/Exness symbol to the yfinance ticker used for analysis."""
    base = _strip_suffix(mt5_symbol)

    if base in _FOREX:
        return f"{base}=X"

    if base in _CRYPTO:
        # BTCUSD → BTC-USD
        quote = base[-3:]
        currency = base[:-3]
        return f"{currency}-{quote}"

    # Stock CFD: Exness uses #AAPL — strip the #
    if base.startswith("#"):
        return base[1:]

    return base


def to_mt5_symbol(user_symbol: str, suffix: str = "") -> str:
    """
    Normalise user input to an MT5 symbol name.

    Args:
        user_symbol: What the user typed (e.g. "eurusd", "BTC-USD", "#AAPL")
        suffix:      Exness account suffix if needed (e.g. "m" → "EURUSDm")
    """
    s = user_symbol.upper().strip()

    # yfinance forex format → MT5  (EURUSD=X → EURUSD)
    if s.endswith("=X"):
        s = s[:-2]

    # Crypto with dash  BTC-USD → BTCUSD
    if "-" in s and not s.startswith("#"):
        s = s.replace("-", "")

    return s + suffix.upper()
