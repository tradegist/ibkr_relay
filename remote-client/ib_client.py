"""IB Gateway client — connection management and order placement."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from ib_async import IB, LimitOrder, MarketOrder, Stock

log = logging.getLogger("ib-client")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IB_HOST = os.environ.get("IB_HOST", "ib-gateway")
TRADING_MODE = os.environ.get("TRADING_MODE", "paper")
IB_PORT = int(os.environ.get(
    "IB_LIVE_PORT" if TRADING_MODE == "live" else "IB_PAPER_PORT", "4004"
))
CLIENT_ID = 1

INITIAL_RETRY_DELAY = 10
MAX_RETRY_DELAY = 300


# ---------------------------------------------------------------------------
# Order result
# ---------------------------------------------------------------------------
@dataclass
class OrderResult:
    status: str
    order_id: int
    action: str
    symbol: str
    quantity: int
    order_type: str
    limit_price: float | None = None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class IBClient:
    """Thin wrapper around ib_async.IB for connection management and orders."""

    def __init__(self) -> None:
        self.ib = IB()
        self._retry_delay = INITIAL_RETRY_DELAY

    @property
    def is_connected(self) -> bool:
        return self.ib.isConnected()

    async def connect(self) -> None:
        """Connect to IB Gateway with exponential backoff retry."""
        while True:
            try:
                log.info("Connecting to IB Gateway at %s:%d ...", IB_HOST, IB_PORT)
                await self.ib.connectAsync(
                    IB_HOST, IB_PORT, clientId=CLIENT_ID, timeout=20
                )
                log.info("Connected — accounts: %s", self.ib.managedAccounts())
                self._retry_delay = INITIAL_RETRY_DELAY
                return
            except Exception as exc:
                log.warning(
                    "Connection failed: %s — retrying in %ds",
                    exc, self._retry_delay,
                )
                await asyncio.sleep(self._retry_delay)
                self._retry_delay = min(self._retry_delay * 2, MAX_RETRY_DELAY)

    def on_disconnect(self) -> None:
        log.warning("Disconnected from IB Gateway — will reconnect")
        asyncio.ensure_future(self._reconnect())

    async def _reconnect(self) -> None:
        await asyncio.sleep(self._retry_delay)
        if not self.is_connected:
            await self.connect()

    async def watchdog(self) -> None:
        """Periodically check the connection and reconnect if stale."""
        while True:
            await asyncio.sleep(30)
            if not self.is_connected:
                log.warning("Watchdog: connection lost — reconnecting")
                await self.connect()

    async def place_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str,
        limit_price: float | None = None,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> OrderResult:
        """Place a stock order and return the result.

        Raises ValueError for invalid input, RuntimeError for IB errors.
        """
        if quantity == 0:
            raise ValueError("quantity cannot be zero")
        if not symbol:
            raise ValueError("symbol is required")

        action = "BUY" if quantity > 0 else "SELL"
        abs_qty = abs(quantity)

        if order_type == "LMT":
            if limit_price is None:
                raise ValueError("limitPrice required for LMT orders")
            order = LimitOrder(action, abs_qty, limit_price)
        elif order_type == "MKT":
            order = MarketOrder(action, abs_qty)
        else:
            raise ValueError(f"Unsupported orderType: {order_type}")

        contract = Stock(symbol, exchange, currency)

        try:
            qualified = await self.ib.qualifyContractsAsync(contract)
            if not qualified:
                raise ValueError(f"Could not qualify contract for {symbol}")
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Contract qualification failed: {exc}") from exc

        log.info(
            "Placing order: %s %d %s %s%s",
            action, abs_qty, symbol, order_type,
            f" @ {limit_price}" if order_type == "LMT" else "",
        )

        try:
            trade = self.ib.placeOrder(contract, order)
        except Exception as exc:
            raise RuntimeError(f"Order placement failed: {exc}") from exc

        # Give IBKR a moment to acknowledge
        await asyncio.sleep(1)

        return OrderResult(
            status=trade.orderStatus.status,
            order_id=trade.order.orderId,
            action=action,
            symbol=symbol,
            quantity=abs_qty,
            order_type=order_type,
            limit_price=limit_price if order_type == "LMT" else None,
        )
