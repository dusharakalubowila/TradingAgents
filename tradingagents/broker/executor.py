"""
Places and closes MT5 orders based on TradingAgents signals.

Signal → Action mapping:
    Buy / Overweight  → BUY market order
    Hold              → no trade
    Underweight / Sell → SELL market order

Fix: Tries ORDER_FILLING_RETURN first (Exness default), falls back to
     FOK and IOC so orders work across all Exness account types.
"""

import logging
import time as _time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from .mt5_client import MT5Client
from .portfolio import Portfolio, TradeRecord
from .position_sizer import PositionSizer
from .risk_guard import RiskGuard, BUY_SIGNALS

logger = logging.getLogger(__name__)

MAGIC = 20240101

SIGNAL_TO_ACTION = {
    "Buy":        "BUY",
    "BUY":        "BUY",
    "Overweight": "BUY",
    "Hold":       None,
    "Underweight":"SELL",
    "Sell":       "SELL",
    "SELL":       "SELL",
}

# Order filling modes to try in order (Exness Standard/Cent prefer RETURN)
_FILLING_MODES = [2, 1, 0]   # RETURN=2, FOK=0, IOC=1 (mt5 constants)
_RETRIES = 2
_RETRY_DELAY = 1.0            # seconds between retries


@dataclass
class OrderResult:
    success: bool
    ticket: Optional[int]
    symbol: str
    action: str
    volume: float
    price: float
    stop_loss: float
    take_profit: float
    message: str


class TradeExecutor:
    """Executes trades via MT5 from agent signals."""

    def __init__(
        self,
        mt5: MT5Client,
        portfolio: Portfolio,
        risk_guard: RiskGuard,
        position_sizer: PositionSizer,
        take_profit_rr: float = 2.0,
        deviation: int = 20,
    ):
        self.mt5 = mt5
        self.portfolio = portfolio
        self.risk_guard = risk_guard
        self.sizer = position_sizer
        self.tp_rr = take_profit_rr
        self.deviation = deviation

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_signal(
        self,
        symbol: str,
        signal: str,
        agent_entry_price: Optional[float] = None,
        agent_stop_loss: Optional[float] = None,
    ) -> OrderResult:
        action = SIGNAL_TO_ACTION.get(signal)
        if not action:
            return OrderResult(False, None, symbol, "NONE", 0, 0, 0, 0,
                               "Signal is Hold — skipped.")

        approved, reason = self.risk_guard.check(signal, symbol)
        if not approved:
            logger.info("Risk guard blocked: %s", reason)
            return OrderResult(False, None, symbol, action, 0, 0, 0, 0, reason)

        # Sync live positions before trading
        self.portfolio.sync_positions_from_mt5(self.mt5, symbol)

        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            return OrderResult(False, None, symbol, action, 0, 0, 0, 0,
                               f"Cannot get tick for {symbol}.")

        entry_price = tick.ask if action == "BUY" else tick.bid
        info = self.mt5.symbol_info(symbol)
        if info is None:
            return OrderResult(False, None, symbol, action, 0, 0, 0, 0,
                               f"Cannot get symbol info for {symbol}.")

        stop_loss, take_profit = self._levels(action, entry_price, agent_stop_loss, info)
        risk_amount = self.risk_guard.max_risk_amount()
        volume = self.sizer.calculate(symbol, entry_price, stop_loss, risk_amount)

        result = self._send_with_retry(symbol, action, volume, entry_price,
                                       stop_loss, take_profit, info)

        if result.success:
            self.portfolio.record_open_trade(TradeRecord(
                ticket=result.ticket,
                symbol=symbol,
                action=action,
                volume=volume,
                open_price=result.price,
                close_price=None,
                stop_loss=stop_loss,
                take_profit=take_profit,
                profit=None,
                open_time=datetime.now().isoformat(),
                close_time=None,
                signal_rating=signal,
                status="open",
            ))

        return result

    def close_position(self, ticket: int) -> OrderResult:
        positions = self.mt5.positions_get()
        position = next((p for p in positions if p.ticket == ticket), None)
        if position is None:
            return OrderResult(False, None, "", "", 0, 0, 0, 0,
                               f"No open position with ticket {ticket}.")

        close_action = "SELL" if position.type == 0 else "BUY"
        tick = self.mt5.symbol_info_tick(position.symbol)
        if tick is None:
            return OrderResult(False, None, position.symbol, close_action,
                               0, 0, 0, 0, "No tick data for close.")

        price = tick.bid if close_action == "SELL" else tick.ask
        info = self.mt5.symbol_info(position.symbol)
        digits = info.digits if info else 5
        order_type = (self.mt5.ORDER_TYPE_SELL if close_action == "SELL"
                      else self.mt5.ORDER_TYPE_BUY)

        for filling in _FILLING_MODES:
            request = {
                "action":   self.mt5.TRADE_ACTION_DEAL,
                "symbol":   position.symbol,
                "volume":   position.volume,
                "type":     order_type,
                "position": position.ticket,
                "price":    round(price, digits),
                "deviation":self.deviation,
                "magic":    MAGIC,
                "comment":  "TradingAgents close",
                "type_time":self.mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }
            result = self.mt5.order_send(request)
            if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
                self.portfolio.record_close_trade(ticket, price, position.profit)
                return OrderResult(True, result.order, position.symbol, close_action,
                                   position.volume, price, 0, 0, "Position closed.")

        err = str(self.mt5.last_error())
        return OrderResult(False, None, position.symbol, close_action,
                           0, 0, 0, 0, f"Close failed: {err}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _levels(self, action, entry, agent_sl, info) -> Tuple[float, float]:
        from .position_sizer import DEFAULT_STOP_PIPS
        dist = abs(entry - agent_sl) if (agent_sl and agent_sl > 0) else DEFAULT_STOP_PIPS * info.point
        d = info.digits
        if action == "BUY":
            return round(entry - dist, d), round(entry + dist * self.tp_rr, d)
        return round(entry + dist, d), round(entry - dist * self.tp_rr, d)

    def _send_with_retry(self, symbol, action, volume, price,
                         stop_loss, take_profit, info) -> OrderResult:
        """Try each filling mode; retry on transient errors."""
        order_type = (self.mt5.ORDER_TYPE_BUY if action == "BUY"
                      else self.mt5.ORDER_TYPE_SELL)
        digits = info.digits
        last_msg = ""

        for attempt in range(_RETRIES):
            # Refresh price on retry
            if attempt > 0:
                tick = self.mt5.symbol_info_tick(symbol)
                if tick:
                    price = tick.ask if action == "BUY" else tick.bid
                _time.sleep(_RETRY_DELAY)

            for filling in _FILLING_MODES:
                request = {
                    "action":       self.mt5.TRADE_ACTION_DEAL,
                    "symbol":       symbol,
                    "volume":       volume,
                    "type":         order_type,
                    "price":        round(price, digits),
                    "sl":           round(stop_loss, digits),
                    "tp":           round(take_profit, digits),
                    "deviation":    self.deviation,
                    "magic":        MAGIC,
                    "comment":      "TradingAgents",
                    "type_time":    self.mt5.ORDER_TIME_GTC,
                    "type_filling": filling,
                }

                logger.info("Order attempt %d filling=%d: %s %s %.2f @ %.5f",
                            attempt + 1, filling, action, symbol, volume, price)

                result = self.mt5.order_send(request)
                if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
                    return OrderResult(
                        success=True, ticket=result.order,
                        symbol=symbol, action=action, volume=volume,
                        price=result.price, stop_loss=stop_loss,
                        take_profit=take_profit,
                        message=f"Filled — ticket {result.order}",
                    )

                last_msg = (f"retcode={result.retcode} {result.comment}"
                            if result else str(self.mt5.last_error()))
                logger.warning("Order failed: %s", last_msg)

        return OrderResult(
            success=False, ticket=None, symbol=symbol, action=action,
            volume=volume, price=price, stop_loss=stop_loss,
            take_profit=take_profit,
            message=f"All attempts failed: {last_msg}",
        )
