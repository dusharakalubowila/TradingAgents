"""
Economic calendar guard — fetches ForexFactory's weekly calendar and
blocks trades within BUFFER_MINUTES of a High-impact news event.

Why: NFP, CPI, Fed decisions cause 50-200 pip spikes in seconds.
     A 30-pip stop gets hit instantly; a $100 account can't absorb that.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import urllib.request
import json
import re

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
BUFFER_MINUTES = 30     # block trading this many minutes before/after event
HIGH_IMPACT_ONLY = True # only block on "High" impact events

# Currency → relevant forex symbols
_CURRENCY_SYMBOLS = {
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD", "NZDUSD", "XAUUSD"],
    "EUR": ["EURUSD", "EURGBP", "EURJPY", "EURAUD", "EURCHF"],
    "GBP": ["GBPUSD", "EURGBP", "GBPJPY", "GBPAUD", "GBPCAD"],
    "JPY": ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY"],
    "AUD": ["AUDUSD", "AUDCAD", "AUDJPY", "EURAUD", "GBPAUD"],
    "CAD": ["USDCAD", "AUDCAD", "CADJPY", "GBPCAD"],
    "CHF": ["USDCHF", "EURCHF", "GBPCHF"],
    "NZD": ["NZDUSD", "NZDCAD", "NZDJPY"],
}


def _fetch_calendar() -> List[dict]:
    try:
        req = urllib.request.Request(
            CALENDAR_URL,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning("Could not fetch economic calendar: %s — skipping news filter.", e)
        return []


def _parse_event_time(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse ForexFactory date/time strings to UTC datetime."""
    try:
        # date: "2026-05-04", time: "08:30am" or "All Day" or "Tentative"
        if not time_str or time_str.lower() in ("all day", "tentative", ""):
            # Treat all-day events as high-risk all day
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return d.replace(hour=0, minute=0, tzinfo=timezone.utc)

        time_str = time_str.strip().lower()
        # Handle "8:30am" or "08:30am"
        m = re.match(r"(\d{1,2}):(\d{2})(am|pm)", time_str)
        if not m:
            return None
        hour, minute, meridiem = int(m.group(1)), int(m.group(2)), m.group(3)
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0

        d = datetime.strptime(date_str, "%Y-%m-%d")
        # ForexFactory times are US Eastern — convert to UTC (EST = UTC-5, EDT = UTC-4)
        # Use UTC-5 as conservative estimate
        utc_hour = (hour + 5) % 24
        return d.replace(hour=utc_hour, minute=minute, tzinfo=timezone.utc)
    except Exception:
        return None


class NewsCalendar:
    """Checks whether a trade should be blocked due to upcoming high-impact news."""

    def __init__(self, buffer_minutes: int = BUFFER_MINUTES):
        self.buffer = timedelta(minutes=buffer_minutes)
        self._events: Optional[List[dict]] = None

    def _load(self):
        if self._events is None:
            self._events = _fetch_calendar()

    def is_news_window(self, mt5_symbol: str) -> tuple:
        """
        Returns (blocked: bool, reason: str).
        blocked=True means skip this trade.
        """
        self._load()
        if not self._events:
            return False, ""

        now = datetime.now(timezone.utc)
        base = mt5_symbol.upper().rstrip("CM")   # strip cent/mini suffixes

        # Find which currencies are in this symbol
        relevant_currencies = [
            cur for cur, syms in _CURRENCY_SYMBOLS.items()
            if any(base.startswith(s[:3]) or base.endswith(s[-3:]) or s in base for s in syms)
        ]
        # Fallback: first 3 and last 3 chars
        if not relevant_currencies:
            relevant_currencies = [base[:3], base[3:6]] if len(base) >= 6 else [base[:3]]

        for event in self._events:
            if HIGH_IMPACT_ONLY and event.get("impact", "").lower() != "high":
                continue
            if event.get("country", "").upper() not in relevant_currencies:
                continue

            event_time = _parse_event_time(
                event.get("date", ""), event.get("time", "")
            )
            if event_time is None:
                continue

            if abs((event_time - now).total_seconds()) <= self.buffer.total_seconds():
                return True, (
                    f"High-impact news in {int(self.buffer.total_seconds() / 60)} min window: "
                    f"{event.get('title', 'Unknown')} ({event.get('country', '')})"
                )

        return False, ""

    def next_events(self, mt5_symbol: str, n: int = 3) -> List[dict]:
        """Return the next N high-impact events for this symbol's currencies."""
        self._load()
        now = datetime.now(timezone.utc)
        base = mt5_symbol.upper().rstrip("CM")
        relevant = [base[:3], base[3:6]] if len(base) >= 6 else [base[:3]]

        upcoming = []
        for event in self._events:
            if event.get("impact", "").lower() != "high":
                continue
            if event.get("country", "").upper() not in relevant:
                continue
            t = _parse_event_time(event.get("date", ""), event.get("time", ""))
            if t and t > now:
                upcoming.append({**event, "_utc": t})

        upcoming.sort(key=lambda e: e["_utc"])
        return upcoming[:n]
