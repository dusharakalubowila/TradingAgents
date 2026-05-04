"""
Trading session filter — only allows trades during high-liquidity sessions.

Sessions (UTC):
  London   08:00 – 17:00   best for EUR, GBP pairs
  New York 13:30 – 22:00   best for USD pairs, US stocks
  Overlap  13:30 – 17:00   highest liquidity window

Sri Lanka time (UTC+5:30):
  London session  → 13:30 – 22:30 LKT
  NY session      → 19:00 – 03:30 LKT
  Overlap         → 19:00 – 22:30 LKT  ← best time to trade
"""

import logging
from datetime import datetime, time, timezone
from enum import Enum
from typing import Tuple

logger = logging.getLogger(__name__)


class SessionType(str, Enum):
    LONDON   = "London"
    NEW_YORK = "New York"
    OVERLAP  = "London/NY Overlap"
    ASIAN    = "Asian"
    CLOSED   = "Closed"


# All times in UTC
_SESSIONS = {
    SessionType.LONDON:   (time(8,  0), time(17, 0)),
    SessionType.NEW_YORK: (time(13, 30), time(22, 0)),
    SessionType.ASIAN:    (time(0,  0), time(9,  0)),
}

# Stock market hours UTC (NYSE/NASDAQ regular + pre-market)
_STOCK_PREMARKET = (time(10, 0), time(13, 30))
_STOCK_REGULAR   = (time(13, 30), time(20, 0))


def _in_range(t: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= t <= end
    # Overnight range (wraps midnight)
    return t >= start or t <= end


def current_session(utc_now: datetime = None) -> SessionType:
    """Return the active trading session for the current UTC time."""
    t = (utc_now or datetime.now(timezone.utc)).time()

    in_london = _in_range(t, *_SESSIONS[SessionType.LONDON])
    in_ny     = _in_range(t, *_SESSIONS[SessionType.NEW_YORK])
    in_asian  = _in_range(t, *_SESSIONS[SessionType.ASIAN])

    if in_london and in_ny:
        return SessionType.OVERLAP
    if in_london:
        return SessionType.LONDON
    if in_ny:
        return SessionType.NEW_YORK
    if in_asian:
        return SessionType.ASIAN
    return SessionType.CLOSED


def is_forex_tradeable(utc_now: datetime = None) -> Tuple[bool, str]:
    """
    Returns (allowed, reason).
    Allows trading during London, NY, and Overlap sessions only.
    """
    session = current_session(utc_now)
    t = (utc_now or datetime.now(timezone.utc)).time()

    if session in (SessionType.LONDON, SessionType.NEW_YORK, SessionType.OVERLAP):
        return True, f"Active session: {session.value}"

    if session == SessionType.ASIAN:
        return False, (
            "Asian session — low liquidity, wide spreads. "
            "London opens at 08:00 UTC (13:30 LKT)."
        )

    # Closed — find next session
    next_open = "08:00 UTC (13:30 LKT)"
    return False, f"Market between sessions. Next: London at {next_open}."


def is_stock_tradeable(utc_now: datetime = None) -> Tuple[bool, str]:
    """
    Returns (allowed, reason) for US stock CFDs.
    Allows pre-market and regular session.
    """
    t = (utc_now or datetime.now(timezone.utc)).time()

    if _in_range(t, *_STOCK_REGULAR):
        return True, "NYSE/NASDAQ regular session (13:30–20:00 UTC)."

    if _in_range(t, *_STOCK_PREMARKET):
        return True, "Pre-market session (10:00–13:30 UTC)."

    return False, (
        "US stock market closed. "
        "Pre-market opens 10:00 UTC (15:30 LKT), "
        "regular session 13:30 UTC (19:00 LKT)."
    )


def is_tradeable(mt5_symbol: str, utc_now: datetime = None) -> Tuple[bool, str]:
    """
    Unified check — detects symbol type and applies correct session filter.
    """
    from .symbol_mapper import is_stock
    if is_stock(mt5_symbol):
        return is_stock_tradeable(utc_now)
    return is_forex_tradeable(utc_now)


def session_info() -> str:
    """Human-readable current session status."""
    now = datetime.now(timezone.utc)
    session = current_session(now)
    # Convert to Sri Lanka time (UTC+5:30)
    from datetime import timedelta
    lkt = now + timedelta(hours=5, minutes=30)
    return (
        f"UTC: {now.strftime('%H:%M')}  |  "
        f"LKT: {lkt.strftime('%H:%M')}  |  "
        f"Session: {session.value}"
    )
