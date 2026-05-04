"""
Maps between MT5/Exness symbol names and yfinance tickers.

MT5 symbol   →   yfinance ticker
  EURUSD     →   EURUSD=X
  EURUSDc    →   EURUSD=X   (Standard Cent suffix stripped)
  EURUSDm    →   EURUSD=X   (Mini suffix stripped)
  BTCUSD     →   BTC-USD
  #AAPL      →   AAPL
  AAPL       →   AAPL
"""

_FOREX = {
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF",
    "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "EURAUD", "EURCHF",
    "AUDJPY", "CADJPY", "GBPAUD", "GBPCAD", "CHFJPY", "EURSGD",
    "XAUUSD", "XAGUSD", "XPTUSD",
}

_CRYPTO = {
    "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "BNBUSD", "SOLUSD",
    "ADAUSD", "DOTUSD", "DOGEUSD", "LINKUSD", "MATICUSD", "AVAXUSD",
}

# Known Exness account-type suffixes to strip
_SUFFIXES = (".EXNESS", "PRO", "ECN", "STP", "C", "M")


def _strip_suffix(symbol: str) -> str:
    """Remove Exness account/platform suffixes and return base symbol."""
    s = symbol.upper()
    for suf in _SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf) + 3:
            return s[: -len(suf)]
    return s


def is_forex(mt5_symbol: str) -> bool:
    return _strip_suffix(mt5_symbol) in _FOREX


def is_crypto(mt5_symbol: str) -> bool:
    return _strip_suffix(mt5_symbol) in _CRYPTO


def is_stock(mt5_symbol: str) -> bool:
    """Stocks on Exness use # prefix or are plain tickers not in forex/crypto."""
    s = mt5_symbol.upper()
    if s.startswith("#"):
        return True
    base = _strip_suffix(s)
    return base not in _FOREX and base not in _CRYPTO and len(base) <= 5


def to_yfinance_ticker(mt5_symbol: str) -> str:
    """Convert an MT5/Exness symbol to the yfinance ticker used for analysis."""
    base = _strip_suffix(mt5_symbol)

    if base in _FOREX:
        return f"{base}=X"

    if base in _CRYPTO:
        quote    = base[-3:]
        currency = base[:-3]
        return f"{currency}-{quote}"

    # Stock CFD: Exness uses #AAPL — strip the #
    if base.startswith("#"):
        return base[1:]

    return base


def to_mt5_symbol(user_symbol: str, suffix: str = "") -> str:
    """
    Normalise user input to MT5 symbol format.

    Args:
        user_symbol: e.g. "eurusd", "BTC-USD", "#AAPL", "EURUSDc"
        suffix:      Exness account suffix to append (e.g. "c" → EURUSDc)
    """
    s = user_symbol.upper().strip()

    # Already has the suffix
    if suffix and s.endswith(suffix.upper()):
        return s

    # yfinance forex format: EURUSD=X → EURUSD
    if s.endswith("=X"):
        s = s[:-2]

    # Crypto with dash: BTC-USD → BTCUSD
    if "-" in s and not s.startswith("#"):
        s = s.replace("-", "")

    return s + suffix.upper()


def auto_suffix(mt5_symbol: str, account_type: str) -> str:
    """
    Return the symbol with the correct Exness suffix for the account type.

    account_type: "standard_cent" → appends "c"
                  others          → no change
    """
    if account_type.lower().replace(" ", "_") == "standard_cent":
        base = _strip_suffix(mt5_symbol)
        if not mt5_symbol.upper().endswith("C"):
            return base + "c"
    return mt5_symbol


def get_analysts_for_symbol(mt5_symbol: str) -> list:
    """
    Return the optimal analyst list for this symbol type.
    Stocks → all 4; Forex/Crypto → market + news only.
    """
    if is_stock(mt5_symbol):
        return ["market", "social", "news", "fundamentals"]
    return ["market", "news"]
