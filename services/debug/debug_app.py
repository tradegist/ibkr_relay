"""Debug webhook inbox — captures webhook payloads for inspection."""

import json
import logging
import os
from datetime import UTC, datetime

from aiohttp import web

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("debug-webhook")

HTTP_PORT = 9000
DEBUG_PATH = os.environ.get("DEBUG_WEBHOOK_PATH", "")
MAX_PAYLOADS = min(int(os.environ.get("MAX_DEBUG_WEBHOOK_PAYLOADS", "100")), 150)

PayloadEntry = dict[str, object]
_inbox: list[PayloadEntry] = []


def _path_matches(request: web.Request) -> bool:
    path = request.match_info.get("path", "")
    if not DEBUG_PATH or path != DEBUG_PATH:
        raise web.HTTPNotFound()
    return True


async def handle_post(request: web.Request) -> web.Response:
    """Capture incoming webhook payload and headers."""
    _path_matches(request)

    try:
        payload = await request.json()
    except Exception:
        payload = (await request.read()).decode("utf-8", errors="replace")

    headers = dict(request.headers)

    entry: PayloadEntry = {
        "payload": payload,
        "headers": headers,
        "received_at": datetime.now(UTC).isoformat(),
    }

    _inbox.append(entry)
    while len(_inbox) > MAX_PAYLOADS:
        _inbox.pop(0)

    log.info("Captured webhook payload (%d/%d stored)", len(_inbox), MAX_PAYLOADS)
    log.debug("Entry:\n%s", json.dumps(entry, indent=2, default=str))

    return web.json_response({"payload": payload, "headers": headers})


async def handle_get(request: web.Request) -> web.Response:
    """Return all stored payloads."""
    _path_matches(request)
    return web.json_response({"payloads": _inbox, "count": len(_inbox)})


async def handle_delete(request: web.Request) -> web.Response:
    """Clear all stored payloads."""
    _path_matches(request)
    _inbox.clear()
    log.info("Debug webhook inbox cleared")
    return web.json_response({"cleared": True})


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "debug_path_configured": bool(DEBUG_PATH)})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/debug/webhook/{path}", handle_post)
    app.router.add_get("/debug/webhook/{path}", handle_get)
    app.router.add_delete("/debug/webhook/{path}", handle_delete)
    app.router.add_get("/health", handle_health)
    return app


if __name__ == "__main__":
    if DEBUG_PATH:
        log.info(
            "Debug webhook inbox starting on port %d (path=/debug/webhook/%s, max=%d)",
            HTTP_PORT,
            DEBUG_PATH,
            MAX_PAYLOADS,
        )
    else:
        log.info(
            "Debug webhook inbox starting on port %d (no DEBUG_WEBHOOK_PATH — all requests return 404)",
            HTTP_PORT,
        )
    web.run_app(create_app(), host="0.0.0.0", port=HTTP_PORT, print=None)
