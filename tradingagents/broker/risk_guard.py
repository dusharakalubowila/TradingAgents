"""
Risk management gate — every trade must pass all checks before execution.
Protects the $100 account from blowing up on a single bad run.
"""

import logging
from dataclasses import dataclass
from typing import Tuple

from .portfolio import Portfolio

logger = logging.getLogger(__name__)

# Signals that clearly point in one direction
BUY_SIGNALS = {"Buy", "BUY", "Overweight"}
SELL_SIGNALS = {"Sell", "SELL", "Underweight"}


@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 2.0     # 2% of balance = $2 on $100
    max_daily_loss_pct: float = 5.0         # stop trading after $5 loss in a day
    max_drawdown_pct: float = 20.0          # pause if account drops 20% from peak
    max_open_positions: int = 3
    # "strong" = only Buy / Sell trigger orders; "any" = all non-Hold signals
    min_signal_strength: str = "any"


class RiskGuard:
    """Validates each trade against hard risk limits before execution."""

    def __init__(self, config: RiskConfig, portfolio: Portfolio):
        self.config = config
        self.portfolio = portfolio

    def check(self, signal: str, symbol: str) -> Tuple[bool, str]:
        """
        Returns (approved, reason).
        approved=False means skip this trade.
        """
        state = self.portfolio.state

        # 1. Signal must be actionable
        if signal == "Hold":
            return False, "Signal is Hold — no trade."

        # 2. Strong-only filter
        if self.config.min_signal_strength == "strong":
            if signal not in BUY_SIGNALS and signal not in SELL_SIGNALS:
                return False, f"Signal '{signal}' is not strong enough (need Buy or Sell)."

        # 3. Max drawdown guard — stop trading when account is bleeding
        dd_pct = self.portfolio.drawdown_pct * 100
        if dd_pct >= self.config.max_drawdown_pct:
            return False, (
                f"Max drawdown reached ({dd_pct:.1f}% >= {self.config.max_drawdown_pct:.0f}%). "
                f"Trading paused to protect capital."
            )

        # 4. Max daily loss
        if state.daily_pnl < 0:
            daily_loss_pct = abs(state.daily_pnl) / state.initial_balance * 100
            if daily_loss_pct >= self.config.max_daily_loss_pct:
                return False, (
                    f"Daily loss limit reached (${abs(state.daily_pnl):.2f} = "
                    f"{daily_loss_pct:.1f}%). Resuming tomorrow."
                )

        # 5. Max concurrent open positions
        open_count = len(state.open_trades)
        if open_count >= self.config.max_open_positions:
            return False, (
                f"Max {self.config.max_open_positions} open positions reached "
                f"({open_count} currently open)."
            )

        # 6. No duplicate position in same direction on same symbol
        existing = self.portfolio.get_open_trade_for_symbol(symbol)
        if existing:
            new_action = "BUY" if signal in BUY_SIGNALS else "SELL"
            if existing["action"] == new_action:
                return False, (
                    f"Already have an open {new_action} on {symbol} "
                    f"(ticket {existing['ticket']})."
                )

        return True, "OK"

    def max_risk_amount(self) -> float:
        """Dollar amount we can lose on this trade (risk % of current balance)."""
        return self.portfolio.state.current_balance * (self.config.max_risk_per_trade_pct / 100)
