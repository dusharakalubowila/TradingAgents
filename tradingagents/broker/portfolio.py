"""
Persistent portfolio state — tracks the $100 balance, open trades, and P&L
across runs by saving state to a JSON file.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    ticket: int
    symbol: str
    action: str             # "BUY" or "SELL"
    volume: float
    open_price: float
    close_price: Optional[float]
    stop_loss: float
    take_profit: float
    profit: Optional[float]
    open_time: str
    close_time: Optional[str]
    signal_rating: str      # Buy / Overweight / Hold / Underweight / Sell
    status: str             # "open" or "closed"


@dataclass
class PortfolioState:
    initial_balance: float = 100.0
    current_balance: float = 100.0
    peak_balance: float = 100.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    daily_pnl: float = 0.0
    daily_reset_date: str = field(default_factory=lambda: date.today().isoformat())
    open_trades: List[Dict] = field(default_factory=list)
    closed_trades: List[Dict] = field(default_factory=list)


class Portfolio:
    """Persistent portfolio tracker — load/save state to JSON."""

    def __init__(self, state_path: str):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> PortfolioState:
        if self.state_path.exists():
            try:
                with open(self.state_path, encoding="utf-8") as f:
                    data = json.load(f)
                return PortfolioState(**data)
            except Exception as e:
                logger.warning("Could not load portfolio state: %s — starting fresh.", e)
        return PortfolioState()

    def _save(self):
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.state), f, indent=2)

    # ------------------------------------------------------------------
    # Sync & mutations
    # ------------------------------------------------------------------

    def sync_balance(self, mt5_balance: float):
        """Pull live balance from MT5 account; reset daily P&L on new day."""
        self.state.current_balance = mt5_balance
        if mt5_balance > self.state.peak_balance:
            self.state.peak_balance = mt5_balance

        today = date.today().isoformat()
        if self.state.daily_reset_date != today:
            self.state.daily_pnl = 0.0
            self.state.daily_reset_date = today

        self._save()

    def record_open_trade(self, trade: TradeRecord):
        self.state.open_trades.append(asdict(trade))
        self.state.total_trades += 1
        self._save()
        logger.info(
            "Trade opened: %s %s  %.2f lots @ %.5f  SL=%.5f  TP=%.5f",
            trade.action, trade.symbol, trade.volume,
            trade.open_price, trade.stop_loss, trade.take_profit,
        )

    def record_close_trade(self, ticket: int, close_price: float, profit: float):
        for t in self.state.open_trades:
            if t["ticket"] == ticket:
                t["close_price"] = close_price
                t["profit"] = profit
                t["close_time"] = datetime.now().isoformat()
                t["status"] = "closed"
                self.state.closed_trades.append(t)
                self.state.open_trades.remove(t)
                self.state.total_profit += profit
                self.state.daily_pnl += profit
                if profit >= 0:
                    self.state.winning_trades += 1
                else:
                    self.state.losing_trades += 1
                self._save()
                logger.info("Trade closed: ticket=%d  profit=%.2f", ticket, profit)
                return

    def get_open_trade_for_symbol(self, symbol: str) -> Optional[Dict]:
        for t in self.state.open_trades:
            if t["symbol"] == symbol:
                return t
        return None

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    @property
    def drawdown_pct(self) -> float:
        if self.state.peak_balance == 0:
            return 0.0
        return (self.state.peak_balance - self.state.current_balance) / self.state.peak_balance

    @property
    def win_rate(self) -> float:
        total = self.state.winning_trades + self.state.losing_trades
        return self.state.winning_trades / total if total > 0 else 0.0

    def summary(self) -> str:
        s = self.state
        return (
            f"Balance : ${s.current_balance:.2f}  (started: ${s.initial_balance:.2f})\n"
            f"Total P&L: ${s.total_profit:+.2f}   Daily P&L: ${s.daily_pnl:+.2f}\n"
            f"Drawdown : {self.drawdown_pct * 100:.1f}%\n"
            f"Win Rate : {self.win_rate * 100:.1f}%\n"
            f"Trades   : {s.total_trades} total  "
            f"({s.winning_trades}W / {s.losing_trades}L)\n"
            f"Open     : {len(s.open_trades)} position(s)"
        )
