"""IBKR Remote Client — maintains a connection to IB Gateway.

Currently stays connected and logs portfolio/order activity.
Future: expose a small HTTP API for placing orders.
"""

import asyncio
import logging
import os

from ib_async import IB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("remote-client")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IB_HOST = os.environ.get("IB_HOST", "ib-gateway")
TRADING_MODE = os.environ.get("TRADING_MODE", "paper")
IB_PORT = int(os.environ.get("IB_LIVE_PORT" if TRADING_MODE == "live" else "IB_PAPER_PORT", "4004"))
CLIENT_ID = 1

INITIAL_RETRY_DELAY = 10
MAX_RETRY_DELAY = 300
retry_delay = INITIAL_RETRY_DELAY


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------
ib = IB()


async def connect():
    global retry_delay
    while True:
        try:
            log.info("Connecting to IB Gateway at %s:%d ...", IB_HOST, IB_PORT)
            await ib.connectAsync(IB_HOST, IB_PORT, clientId=CLIENT_ID, timeout=20)
            log.info("Connected — accounts: %s", ib.managedAccounts())
            retry_delay = INITIAL_RETRY_DELAY
            return
        except Exception as exc:
            log.warning(
                "Connection failed: %s — retrying in %ds", exc, retry_delay
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)


def on_disconnect():
    log.warning("Disconnected from IB Gateway — will reconnect")
    asyncio.ensure_future(reconnect())


async def reconnect():
    await asyncio.sleep(retry_delay)
    await connect()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def amain():
    log.info("IBKR Remote Client starting (mode=%s)", TRADING_MODE)

    await connect()

    ib.disconnectedEvent += on_disconnect

    log.info("Remote client ready. Keeping connection alive ...")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(amain())
