"""
MT5 connection wrapper — works on Windows (MetaTrader5 package)
and Linux (mt5linux package via Wine).

Linux setup:
    1. sudo apt install wine64 winetricks
    2. Download MT5 terminal from your Exness account, install under Wine
    3. pip install mt5linux
    4. Start the server: python -m mt5linux (inside the Wine Python env)
    See: https://github.com/lucas-campagna/mt5linux
"""

import logging
import platform
from dataclasses import dataclass
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def _load_mt5_module(host: str, port: int) -> Any:
    if platform.system() == "Windows":
        try:
            import MetaTrader5 as mt5  # type: ignore
            return mt5
        except ImportError:
            raise ImportError(
                "MetaTrader5 package not found.\n"
                "Install: pip install MetaTrader5\n"
                "Requires MT5 terminal installed on Windows."
            )
    else:
        try:
            from mt5linux import MetaTrader5  # type: ignore
            return MetaTrader5(host=host, port=port)
        except ImportError:
            raise ImportError(
                "On Linux, mt5linux is required.\n\n"
                "Setup steps:\n"
                "  1. Install Wine:  sudo apt install wine64 winetricks\n"
                "  2. Download MT5 from your Exness account and install under Wine\n"
                "  3. pip install mt5linux\n"
                "  4. Start server:  python -m mt5linux  (inside Wine Python env)\n"
                "  Docs: https://github.com/lucas-campagna/mt5linux"
            )


@dataclass
class AccountInfo:
    login: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    currency: str
    leverage: int
    profit: float


@dataclass
class SymbolInfo:
    name: str
    digits: int
    point: float
    trade_tick_value: float
    trade_tick_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    spread: int
    trade_contract_size: float


@dataclass
class Tick:
    bid: float
    ask: float
    last: float
    time: int


@dataclass
class Position:
    ticket: int
    symbol: str
    type: int       # 0 = BUY, 1 = SELL
    volume: float
    open_price: float
    sl: float
    tp: float
    profit: float
    comment: str


class MT5Client:
    """Cross-platform MT5 connection wrapper (Windows & Linux/Wine)."""

    # MT5 constants — kept here so callers don't import the raw module
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 1
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self, host: str = "localhost", port: int = 18812):
        self._mt5 = _load_mt5_module(host, port)
        self._initialized = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def initialize(
        self,
        login: int = None,
        password: str = None,
        server: str = None,
    ) -> bool:
        kwargs = {}
        if login:
            kwargs["login"] = login
        if password:
            kwargs["password"] = password
        if server:
            kwargs["server"] = server

        result = self._mt5.initialize(**kwargs) if kwargs else self._mt5.initialize()
        if result:
            self._initialized = True
            info = self.account_info()
            if info:
                logger.info(
                    "MT5 connected: login=%d  balance=%.2f %s  leverage=1:%d",
                    info.login, info.balance, info.currency, info.leverage,
                )
        else:
            logger.error("MT5 initialize failed: %s", self._mt5.last_error())
        return result

    def shutdown(self):
        if self._initialized:
            self._mt5.shutdown()
            self._initialized = False

    # ------------------------------------------------------------------
    # Account & symbol data
    # ------------------------------------------------------------------

    def account_info(self) -> Optional[AccountInfo]:
        raw = self._mt5.account_info()
        if raw is None:
            return None
        return AccountInfo(
            login=raw.login,
            balance=raw.balance,
            equity=raw.equity,
            margin=raw.margin,
            free_margin=raw.margin_free,
            margin_level=raw.margin_level if raw.margin_level else 0.0,
            currency=raw.currency,
            leverage=raw.leverage,
            profit=raw.profit,
        )

    def symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        raw = self._mt5.symbol_info(symbol)
        if raw is None:
            return None
        return SymbolInfo(
            name=raw.name,
            digits=raw.digits,
            point=raw.point,
            trade_tick_value=raw.trade_tick_value,
            trade_tick_size=raw.trade_tick_size,
            volume_min=raw.volume_min,
            volume_max=raw.volume_max,
            volume_step=raw.volume_step,
            spread=raw.spread,
            trade_contract_size=raw.trade_contract_size,
        )

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        return self._mt5.symbol_select(symbol, enable)

    def symbol_info_tick(self, symbol: str) -> Optional[Tick]:
        raw = self._mt5.symbol_info_tick(symbol)
        if raw is None:
            return None
        return Tick(bid=raw.bid, ask=raw.ask, last=raw.last, time=raw.time)

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def positions_get(self, symbol: str = None) -> List[Position]:
        raw_list = (
            self._mt5.positions_get(symbol=symbol)
            if symbol
            else self._mt5.positions_get()
        )
        if raw_list is None:
            return []
        return [
            Position(
                ticket=p.ticket,
                symbol=p.symbol,
                type=p.type,
                volume=p.volume,
                open_price=p.price_open,
                sl=p.sl,
                tp=p.tp,
                profit=p.profit,
                comment=p.comment,
            )
            for p in raw_list
        ]

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def order_send(self, request: dict) -> Any:
        return self._mt5.order_send(request)

    def last_error(self):
        return self._mt5.last_error()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()
