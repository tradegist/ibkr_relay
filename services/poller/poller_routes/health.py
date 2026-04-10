"""GET /health — poller status."""

from aiohttp import web

from poller_models import HealthResponse


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response(HealthResponse(status="ok").model_dump())
