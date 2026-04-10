"""IBKR Remote Client — entrypoint.

Starts the IB Gateway connection and HTTP API server.
"""

import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web

from client import IBClient, get_trading_mode
from client.listener import ListenerNamespace
from dedup import init_db
from notifier import load_notifiers
from rc_routes import create_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("remote-client")


def get_api_port() -> int:
    raw = os.environ.get("API_PORT", "5000").strip()
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(
            f"Invalid API_PORT={raw!r} — must be an integer"
        ) from None


def get_dedup_db_path() -> str:
    return os.environ.get("DEDUP_DB_PATH", "/data/dedup/fills.db").strip()


def get_debounce_ms() -> int:
    raw = os.environ.get("LISTENER_EVENT_DEBOUNCE_TIME", "0").strip()
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(
            f"Invalid LISTENER_EVENT_DEBOUNCE_TIME={raw!r} — must be an integer"
        ) from None


def get_listener_enabled() -> bool:
    flag = os.environ.get("LISTENER_ENABLED", "").strip().lower()
    return bool(flag and flag not in ("0", "false", "no"))


def get_listener_exec_events_enabled() -> bool:
    flag = os.environ.get("LISTENER_EXEC_EVENTS_ENABLED", "").strip().lower()
    return bool(flag and flag not in ("0", "false", "no"))


async def amain() -> None:
    api_port = get_api_port()
    dedup_db_path = get_dedup_db_path()
    debounce_ms = get_debounce_ms()

    client = IBClient()

    log.info("IBKR Remote Client starting (mode=%s)", get_trading_mode())

    await client.connect()

    client.ib.disconnectedEvent += client.on_disconnect

    # Start listener if enabled
    if get_listener_enabled():
        db_path = Path(dedup_db_path)
        db = init_db(db_path)
        notifiers = load_notifiers()
        exec_events_enabled = get_listener_exec_events_enabled()
        client.listener = ListenerNamespace(
            client.ib, notifiers, db,
            debounce_ms=debounce_ms,
            exec_events_enabled=exec_events_enabled,
        )
        client.listener.start()
        log.info(
            "Listener enabled — subscribed to trade events (exec_events=%s)",
            exec_events_enabled,
        )

    # Start watchdog to detect stale connections
    watchdog_task = asyncio.ensure_future(client.watchdog())
    client._background_tasks.add(watchdog_task)
    watchdog_task.add_done_callback(client._background_tasks.discard)

    log.info("Remote client ready. Starting HTTP API on port %d ...", api_port)

    app = create_routes(client)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", api_port)
    await site.start()

    log.info("HTTP API listening on 0.0.0.0:%d", api_port)

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(amain())
