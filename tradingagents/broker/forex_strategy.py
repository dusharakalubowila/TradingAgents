"""
Forex strategy engine — three institutional strategies.

Strategy 1: London Breakout (GBPUSD primary, EURUSD secondary)
  – Trade the breakout from the Asian session range
  – Optimal: 07:00–09:00 UTC. Works anytime with lower confidence.

Strategy 2: ICT/Smart Money Concepts (EURUSD, XAUUSD)
  – Fair Value Gaps + Order Blocks + Break of Structure
  – Optimal: ICT kill zones (02–05 UTC London, 12–15 UTC NY)
  – Works anytime with lower confidence.

Strategy 3: EMA Hybrid Trend (all pairs)
  – 200 EMA (H1) trend filter → 9/21 EMA position (M15) → RSI gate → ADX filter
  – Optimal: 07–11 UTC or 13–16 UTC. Works anytime.

All strategies output a ForexSignal with action, entry, stop_loss, take_profit.
Time-of-day is a CONFIDENCE MODIFIER, not a hard gate.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ── Symbol helpers ────────────────────────────────────────────────────────────

_YF_OVERRIDE = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
}

_PIP_SIZE = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001,
    "USDCAD": 0.0001, "USDCHF": 0.0001, "EURGBP": 0.0001, "EURAUD": 0.0001,
    "USDJPY": 0.01,   "EURJPY": 0.01,   "GBPJPY": 0.01,   "AUDJPY": 0.01,
    "XAUUSD": 0.01,   "XAGUSD": 0.001,
}

_KILL_ZONES = {
    "asian":        (dtime(0,  0), dtime(3,  0)),
    "london":       (dtime(2,  0), dtime(5,  0)),
    "ny":           (dtime(12, 0), dtime(15, 0)),
    "london_close": (dtime(15, 0), dtime(17, 0)),
}

_LB_HARD_EXIT = 12


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ForexSignal:
    action:      str            # BUY / SELL / WAIT
    symbol:      str            # MT5 symbol
    strategy:    str            # LONDON_BREAKOUT / ICT_SMC / EMA_HYBRID
    confidence:  float          # 0.0–1.0
    reason:      str
    entry_price: Optional[float] = None
    stop_loss:   Optional[float] = None
    take_profit: Optional[float] = None
    hard_exit_hour_utc: Optional[int] = None


# ── Utilities ─────────────────────────────────────────────────────────────────

def pip_size(mt5_symbol: str) -> float:
    base = mt5_symbol.upper().replace("#", "").replace(".", "")
    for suf in ("C", "M", "ECN", "STP", "PRO"):
        if base.endswith(suf) and len(base) > len(suf) + 3:
            base = base[: -len(suf)]
            break
    return _PIP_SIZE.get(base, 0.0001)


def yf_ticker(mt5_symbol: str) -> str:
    base = mt5_symbol.upper().replace("#", "")
    for suf in ("C", "M", "ECN", "STP", "PRO"):
        if base.endswith(suf) and len(base) > len(suf) + 3:
            base = base[: -len(suf)]
            break
    if base in _YF_OVERRIDE:
        return _YF_OVERRIDE[base]
    return f"{base}=X"


def _in_kill_zone(zone: str, now: datetime = None) -> bool:
    if now is None:
        now = datetime.now(timezone.utc)
    t = now.time().replace(tzinfo=None)
    start, end = _KILL_ZONES[zone]
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end


def _fetch(ticker: str, interval: str, period: str) -> pd.DataFrame:
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        if df.empty:
            logger.warning("Empty data for %s (%s %s)", ticker, interval, period)
            return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]
        return df.dropna()
    except Exception as exc:
        logger.error("yfinance error fetching %s: %s", ticker, exc)
        return pd.DataFrame()


def _time_confidence_modifier(optimal: bool) -> float:
    """Return confidence penalty for off-hours trading."""
    return 0.0 if optimal else -0.10


# ── Strategy 1: London Breakout ───────────────────────────────────────────────

class LondonBreakoutStrategy:
    """
    Asian range breakout — works anytime, optimal at London open (07-09 UTC).
    Checks if current price has broken out of the most recent Asian session range.
    """

    MIN_RANGE_PIPS = 15       # relaxed from 20
    MAX_RANGE_PIPS = 120      # relaxed from 80
    BUFFER_PIPS    = 2
    TP_MULTIPLIER  = 1.5

    def analyze(self, mt5_symbol: str) -> ForexSignal:
        now = datetime.now(timezone.utc)
        in_optimal_window = 7 <= now.hour < 9

        ticker = yf_ticker(mt5_symbol)
        df = _fetch(ticker, interval="1h", period="5d")

        if df.empty or len(df) < 12:
            return ForexSignal("WAIT", mt5_symbol, "LONDON_BREAKOUT", 0.0, "Insufficient H1 data")

        # Asian session candles: 22:00 UTC (previous day) → 07:00 UTC (today)
        asian = df[
            (df.index.hour >= 22) | (df.index.hour < 7)
        ].tail(10)

        if len(asian) < 3:
            return ForexSignal("WAIT", mt5_symbol, "LONDON_BREAKOUT", 0.0,
                               "Not enough Asian session candles")

        asian_high = float(asian["high"].max())
        asian_low  = float(asian["low"].min())
        ps         = pip_size(mt5_symbol)
        range_pips = (asian_high - asian_low) / ps

        if range_pips < self.MIN_RANGE_PIPS:
            return ForexSignal("WAIT", mt5_symbol, "LONDON_BREAKOUT", 0.0,
                               f"Asian range too narrow: {range_pips:.1f} pips (min {self.MIN_RANGE_PIPS})")
        if range_pips > self.MAX_RANGE_PIPS:
            return ForexSignal("WAIT", mt5_symbol, "LONDON_BREAKOUT", 0.0,
                               f"Asian range too wide: {range_pips:.1f} pips (max {self.MAX_RANGE_PIPS})")

        price  = float(df["close"].iloc[-1])
        buf    = self.BUFFER_PIPS * ps
        rng    = asian_high - asian_low

        base_conf = 0.58 + min(0.15, (range_pips - 15) / 300)
        time_mod  = _time_confidence_modifier(in_optimal_window)
        time_note = "" if in_optimal_window else " [off-hours]"

        if price > asian_high + buf:
            sl = asian_high - 0.5 * rng
            tp = price + self.TP_MULTIPLIER * rng
            conf = max(0.40, base_conf + time_mod)
            return ForexSignal(
                "BUY", mt5_symbol, "LONDON_BREAKOUT", conf,
                f"Bullish breakout above {asian_high:.5f} | range={range_pips:.1f} pips{time_note}",
                entry_price=price, stop_loss=sl, take_profit=tp,
                hard_exit_hour_utc=_LB_HARD_EXIT if in_optimal_window else None,
            )

        if price < asian_low - buf:
            sl = asian_low + 0.5 * rng
            tp = price - self.TP_MULTIPLIER * rng
            conf = max(0.40, base_conf + time_mod)
            return ForexSignal(
                "SELL", mt5_symbol, "LONDON_BREAKOUT", conf,
                f"Bearish breakout below {asian_low:.5f} | range={range_pips:.1f} pips{time_note}",
                entry_price=price, stop_loss=sl, take_profit=tp,
                hard_exit_hour_utc=_LB_HARD_EXIT if in_optimal_window else None,
            )

        return ForexSignal("WAIT", mt5_symbol, "LONDON_BREAKOUT", 0.0,
                           f"Price {price:.5f} inside Asian range "
                           f"{asian_low:.5f}–{asian_high:.5f} ({range_pips:.1f} pips)")


# ── Strategy 2: ICT / Smart Money Concepts ───────────────────────────────────

class ICTSMCStrategy:
    """
    ICT Smart Money Concepts: BOS + FVG retest.
    Works anytime — kill zone is a confidence boost, not a gate.
    """

    def analyze(self, mt5_symbol: str) -> ForexSignal:
        now = datetime.now(timezone.utc)

        active_zone = next(
            (z for z in ("london", "ny", "asian", "london_close") if _in_kill_zone(z, now)), None
        )
        in_optimal = active_zone in ("london", "ny")
        time_mod   = _time_confidence_modifier(in_optimal)
        zone_label = active_zone.upper() if active_zone else "OFF-HOURS"

        try:
            from smartmoneyconcepts import smc
        except ImportError:
            return ForexSignal("WAIT", mt5_symbol, "ICT_SMC", 0.0,
                               "Package missing — run: pip install smartmoneyconcepts")

        ticker = yf_ticker(mt5_symbol)
        df = _fetch(ticker, interval="1h", period="7d")
        if df.empty or len(df) < 30:
            return ForexSignal("WAIT", mt5_symbol, "ICT_SMC", 0.0, "Insufficient H1 data")

        ohlc = df[["open", "high", "low", "close"]].copy()
        ps   = pip_size(mt5_symbol)

        try:
            swing  = smc.swing_highs_lows(ohlc, swing_length=5)
            fvg_df = smc.fvg(ohlc, join_consecutive=False)
            bos_df = smc.bos_choch(ohlc, swing)
        except Exception as exc:
            logger.error("SMC calculation error on %s: %s", mt5_symbol, exc)
            return ForexSignal("WAIT", mt5_symbol, "ICT_SMC", 0.0, f"SMC error: {exc}")

        price = float(ohlc["close"].iloc[-1])

        if bos_df is not None and not bos_df.empty and fvg_df is not None and not fvg_df.empty:
            bos_col = next((c for c in bos_df.columns if "BOS" in c.upper()), None)
            fvg_col = next((c for c in fvg_df.columns if "FVG" in c.upper()), None)
            top_col = next((c for c in fvg_df.columns if "Top" in c or "top" in c), None)
            bot_col = next((c for c in fvg_df.columns if "Bottom" in c or "bottom" in c), None)

            if bos_col and fvg_col and top_col and bot_col:
                recent_bullish_bos = (bos_df[bos_col].tail(10) > 0).any()
                recent_bearish_bos = (bos_df[bos_col].tail(10) < 0).any()

                # LONG setup
                if recent_bullish_bos:
                    bull_fvg = fvg_df[
                        (fvg_df[fvg_col] == 1) &
                        (fvg_df[top_col] < price)
                    ].tail(3)
                    if not bull_fvg.empty:
                        fvg_top = float(bull_fvg[top_col].iloc[-1])
                        fvg_bot = float(bull_fvg[bot_col].iloc[-1])
                        if fvg_bot <= price <= fvg_top * 1.003:
                            sl  = fvg_bot - 5 * ps
                            tp  = price + 2.0 * (price - sl)
                            conf = max(0.40, 0.75 + time_mod)
                            return ForexSignal(
                                "BUY", mt5_symbol, "ICT_SMC", conf,
                                f"Bullish BOS + FVG retest {fvg_bot:.5f}–{fvg_top:.5f} "
                                f"({zone_label})",
                                entry_price=price, stop_loss=sl, take_profit=tp,
                            )

                # SHORT setup
                if recent_bearish_bos:
                    bear_fvg = fvg_df[
                        (fvg_df[fvg_col] == -1) &
                        (fvg_df[bot_col] > price)
                    ].tail(3)
                    if not bear_fvg.empty:
                        fvg_top = float(bear_fvg[top_col].iloc[-1])
                        fvg_bot = float(bear_fvg[bot_col].iloc[-1])
                        if fvg_bot * 0.997 <= price <= fvg_top:
                            sl  = fvg_top + 5 * ps
                            tp  = price - 2.0 * (sl - price)
                            conf = max(0.40, 0.75 + time_mod)
                            return ForexSignal(
                                "SELL", mt5_symbol, "ICT_SMC", conf,
                                f"Bearish BOS + FVG retest {fvg_bot:.5f}–{fvg_top:.5f} "
                                f"({zone_label})",
                                entry_price=price, stop_loss=sl, take_profit=tp,
                            )

        return ForexSignal("WAIT", mt5_symbol, "ICT_SMC", 0.0,
                           f"No BOS+FVG confluence ({zone_label}, price={price:.5f})")


# ── Strategy 3: EMA Hybrid ────────────────────────────────────────────────────

class EMAHybridStrategy:
    """
    200 EMA (H1) trend + 9/21 EMA (M15) + RSI + ADX.
    Works anytime. Optimal hours boost confidence.

    Key change: doesn't require exact crossover on last bar —
    checks if EMAs are positioned correctly (9 > 21 for bull, 9 < 21 for bear)
    and RSI is in range. This produces signals much more frequently.
    """

    ADX_THRESHOLD  = 18       # relaxed from 20
    RSI_BULL_MIN   = 40       # relaxed from 45
    RSI_BULL_MAX   = 72       # relaxed from 68
    RSI_BEAR_MIN   = 28       # relaxed from 32
    RSI_BEAR_MAX   = 60       # relaxed from 55
    SL_ATR_MULT    = 1.5
    TP_ATR_MULT    = 3.0

    def analyze(self, mt5_symbol: str) -> ForexSignal:
        now = datetime.now(timezone.utc)
        h   = now.hour
        in_optimal = (7 <= h < 11 or 13 <= h < 16)
        time_mod   = _time_confidence_modifier(in_optimal)
        time_note  = "" if in_optimal else " [off-hours]"

        try:
            import ta
        except ImportError:
            return ForexSignal("WAIT", mt5_symbol, "EMA_HYBRID", 0.0,
                               "Package missing — run: pip install ta")

        ticker = yf_ticker(mt5_symbol)
        h1  = _fetch(ticker, interval="1h",  period="30d")
        m15 = _fetch(ticker, interval="15m", period="5d")

        if h1.empty or len(h1) < 210:
            return ForexSignal("WAIT", mt5_symbol, "EMA_HYBRID", 0.0,
                               f"Need 200+ H1 bars, got {len(h1)}")
        if m15.empty or len(m15) < 30:
            return ForexSignal("WAIT", mt5_symbol, "EMA_HYBRID", 0.0,
                               f"Need 30+ M15 bars, got {len(m15)}")

        # H1 indicators
        ema200 = ta.trend.EMAIndicator(h1["close"], window=200).ema_indicator()
        adx    = ta.trend.ADXIndicator(h1["high"], h1["low"], h1["close"],
                                        window=14).adx()

        h1_price   = float(h1["close"].iloc[-1])
        ema200_val = float(ema200.iloc[-1])
        adx_val    = float(adx.iloc[-1])

        if adx_val < self.ADX_THRESHOLD:
            return ForexSignal("WAIT", mt5_symbol, "EMA_HYBRID", 0.0,
                               f"ADX {adx_val:.1f} < {self.ADX_THRESHOLD} — ranging market")

        trend = "BULL" if h1_price > ema200_val else "BEAR"

        # M15 indicators
        ema9  = ta.trend.EMAIndicator(m15["close"], window=9).ema_indicator()
        ema21 = ta.trend.EMAIndicator(m15["close"], window=21).ema_indicator()
        rsi   = ta.momentum.RSIIndicator(m15["close"], window=14).rsi()
        atr   = ta.volatility.AverageTrueRange(
            m15["high"], m15["low"], m15["close"], window=14
        ).average_true_range()

        e9_now  = float(ema9.iloc[-1])
        e21_now = float(ema21.iloc[-1])
        e9_prev  = float(ema9.iloc[-2])
        e21_prev = float(ema21.iloc[-2])
        rsi_val = float(rsi.iloc[-1])
        atr_val = float(atr.iloc[-1])
        price   = float(m15["close"].iloc[-1])

        # Check for crossover (exact bar) OR positioned correctly (EMA alignment)
        golden_cross = e9_now > e21_now and e9_prev <= e21_prev
        death_cross  = e9_now < e21_now and e9_prev >= e21_prev

        # EMA positioning: 9 EMA above/below 21 EMA (no crossover required)
        ema_bullish = e9_now > e21_now
        ema_bearish = e9_now < e21_now

        # Extra confidence for crossover on this bar vs just positioned
        cross_bonus = 0.08 if golden_cross or death_cross else 0.0
        adx_bonus   = 0.08 if adx_val > 30 else 0.0

        # BULL setup: H1 above EMA200, M15 EMAs bullish, RSI in range
        if trend == "BULL" and ema_bullish and self.RSI_BULL_MIN <= rsi_val <= self.RSI_BULL_MAX:
            sl = price - self.SL_ATR_MULT * atr_val
            tp = price + self.TP_ATR_MULT * atr_val
            conf = max(0.40, 0.55 + cross_bonus + adx_bonus + time_mod)
            signal_type = "Golden cross" if golden_cross else "EMA9>EMA21"
            return ForexSignal(
                "BUY", mt5_symbol, "EMA_HYBRID", conf,
                f"{signal_type} M15 | BULL (H1 {h1_price:.5f} > EMA200 {ema200_val:.5f}) "
                f"| RSI {rsi_val:.0f} | ADX {adx_val:.0f}{time_note}",
                entry_price=price, stop_loss=sl, take_profit=tp,
            )

        # BEAR setup: H1 below EMA200, M15 EMAs bearish, RSI in range
        if trend == "BEAR" and ema_bearish and self.RSI_BEAR_MIN <= rsi_val <= self.RSI_BEAR_MAX:
            sl = price + self.SL_ATR_MULT * atr_val
            tp = price - self.TP_ATR_MULT * atr_val
            conf = max(0.40, 0.55 + cross_bonus + adx_bonus + time_mod)
            signal_type = "Death cross" if death_cross else "EMA9<EMA21"
            return ForexSignal(
                "SELL", mt5_symbol, "EMA_HYBRID", conf,
                f"{signal_type} M15 | BEAR (H1 {h1_price:.5f} < EMA200 {ema200_val:.5f}) "
                f"| RSI {rsi_val:.0f} | ADX {adx_val:.0f}{time_note}",
                entry_price=price, stop_loss=sl, take_profit=tp,
            )

        return ForexSignal("WAIT", mt5_symbol, "EMA_HYBRID", 0.0,
                           f"No setup | trend={trend} | EMA9{'>' if ema_bullish else '<'}EMA21 "
                           f"| RSI={rsi_val:.0f} | ADX={adx_val:.0f}")


# ── Aggregate runner ──────────────────────────────────────────────────────────

def run_all_strategies(mt5_symbol: str) -> Optional[ForexSignal]:
    """
    Run all three strategies and return the highest-confidence actionable signal.
    Returns None if every strategy says WAIT.
    """
    strategies = [
        LondonBreakoutStrategy(),
        ICTSMCStrategy(),
        EMAHybridStrategy(),
    ]

    actionable = []
    for strat in strategies:
        try:
            sig = strat.analyze(mt5_symbol)
            level = "✅" if sig.action != "WAIT" else "⏳"
            logger.info("%s [%-16s] %s  conf=%.2f  %s",
                        level, sig.strategy, sig.action, sig.confidence, sig.reason)
            if sig.action in ("BUY", "SELL"):
                actionable.append(sig)
        except Exception as exc:
            logger.error("[%s] unhandled error: %s", strat.__class__.__name__, exc)

    if not actionable:
        return None

    # Prefer signals where multiple strategies agree on direction
    buy_signals  = [s for s in actionable if s.action == "BUY"]
    sell_signals = [s for s in actionable if s.action == "SELL"]

    if len(buy_signals) >= 2:
        best = max(buy_signals, key=lambda s: s.confidence)
        best.confidence = min(1.0, best.confidence + 0.10)
        best.reason = f"[{len(buy_signals)}-strategy confluence] " + best.reason
        return best

    if len(sell_signals) >= 2:
        best = max(sell_signals, key=lambda s: s.confidence)
        best.confidence = min(1.0, best.confidence + 0.10)
        best.reason = f"[{len(sell_signals)}-strategy confluence] " + best.reason
        return best

    # Single signal — return highest confidence
    return max(actionable, key=lambda s: s.confidence)
