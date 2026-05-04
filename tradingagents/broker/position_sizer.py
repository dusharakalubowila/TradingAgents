"""
Calculate lot size from risk amount and stop-loss distance.

Formula:
    lots = risk_amount / (stop_distance_in_price * pip_value_per_lot)

where pip_value_per_lot = (trade_tick_value / trade_tick_size) * point
"""

import logging
from typing import Optional

from .mt5_client import MT5Client, SymbolInfo

logger = logging.getLogger(__name__)

# Fallback stop distance (pips) when agent provides no stop_loss
DEFAULT_STOP_PIPS = 30


def _round_to_step(volume: float, step: float) -> float:
    """Round volume DOWN to the nearest valid lot step."""
    return round(int(volume / step) * step, 8)


class PositionSizer:
    """Calculates safe lot sizes given a risk budget and stop distance."""

    def __init__(self, mt5: MT5Client):
        self.mt5 = mt5

    def calculate(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: Optional[float],
        risk_amount: float,
    ) -> float:
        """
        Args:
            symbol:          MT5 symbol (e.g. "EURUSD")
            entry_price:     Proposed fill price
            stop_loss_price: Agent's stop-loss level (None → use DEFAULT_STOP_PIPS)
            risk_amount:     Max $ loss allowed (e.g. 2% of $100 = $2)

        Returns:
            Lot size clamped to [volume_min, volume_max] and rounded to volume_step.
        """
        info = self.mt5.symbol_info(symbol)
        if info is None:
            logger.warning("No symbol info for %s — using minimum lot.", symbol)
            return 0.01

        stop_distance = self._stop_distance(entry_price, stop_loss_price, info)
        if stop_distance <= 0:
            logger.warning("Invalid stop distance for %s — using minimum lot.", symbol)
            return info.volume_min

        # Value of 1 point move for 1.0 lot in account currency
        pip_value_per_lot = (info.trade_tick_value / info.trade_tick_size) * info.point
        if pip_value_per_lot <= 0:
            logger.warning("Cannot compute pip value for %s — using minimum lot.", symbol)
            return info.volume_min

        stop_pips = stop_distance / info.point
        raw_lots = risk_amount / (stop_pips * pip_value_per_lot)

        lots = _round_to_step(raw_lots, info.volume_step)
        lots = max(info.volume_min, min(info.volume_max, lots))

        logger.info(
            "Sizing: %s  entry=%.5f  sl=%.5f  stop=%.1f pips  "
            "risk=$%.2f  → %.2f lots",
            symbol, entry_price,
            stop_loss_price if stop_loss_price else 0,
            stop_pips, risk_amount, lots,
        )
        return lots

    def _stop_distance(
        self,
        entry_price: float,
        stop_loss_price: Optional[float],
        info: SymbolInfo,
    ) -> float:
        if stop_loss_price and stop_loss_price > 0:
            return abs(entry_price - stop_loss_price)
        return DEFAULT_STOP_PIPS * info.point
