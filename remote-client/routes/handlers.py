"""GET /health — connection status."""

from __future__ import annotations

from aiohttp import web

from ib_client import IBClient


async def handle_health(request: web.Request) -> web.Response:
    client: IBClient = request.app["client"]
    from ib_client import TRADING_MODE
    return web.json_response({
        "connected": client.is_connected,
        "tradingMode": TRADING_MODE,
    })
