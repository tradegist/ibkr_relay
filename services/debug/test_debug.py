"""Tests for the debug webhook inbox service."""

import os
import unittest

os.environ["DEBUG_WEBHOOK_PATH"] = "secret-path"
os.environ["MAX_DEBUG_WEBHOOK_PAYLOADS"] = "3"

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from debug_app import _inbox, create_app


class TestDebugWebhookConfigured(AioHTTPTestCase):
    """Tests when DEBUG_WEBHOOK_PATH is set."""

    async def get_application(self) -> web.Application:
        _inbox.clear()
        return create_app()

    async def test_health(self) -> None:
        resp = await self.client.request("GET", "/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["debug_path_configured"] is True

    async def test_post_correct_path(self) -> None:
        payload = {"symbol": "TSLA", "action": "BUY"}
        resp = await self.client.request(
            "POST",
            "/debug/webhook/secret-path",
            json=payload,
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["payload"] == payload
        assert "Content-Type" in data["headers"]

    async def test_post_wrong_path_returns_404(self) -> None:
        resp = await self.client.request(
            "POST",
            "/debug/webhook/wrong-path",
            json={"x": 1},
        )
        assert resp.status == 404

    async def test_get_returns_stored_payloads(self) -> None:
        # Post two payloads
        await self.client.request("POST", "/debug/webhook/secret-path", json={"n": 1})
        await self.client.request("POST", "/debug/webhook/secret-path", json={"n": 2})

        resp = await self.client.request("GET", "/debug/webhook/secret-path")
        assert resp.status == 200
        data = await resp.json()
        assert data["count"] == 2
        assert len(data["payloads"]) == 2
        assert data["payloads"][0]["payload"]["n"] == 1
        assert data["payloads"][1]["payload"]["n"] == 2

    async def test_get_wrong_path_returns_404(self) -> None:
        resp = await self.client.request("GET", "/debug/webhook/wrong-path")
        assert resp.status == 404

    async def test_delete_clears_inbox(self) -> None:
        await self.client.request("POST", "/debug/webhook/secret-path", json={"n": 1})
        resp = await self.client.request("DELETE", "/debug/webhook/secret-path")
        assert resp.status == 200
        data = await resp.json()
        assert data["cleared"] is True

        resp = await self.client.request("GET", "/debug/webhook/secret-path")
        data = await resp.json()
        assert data["count"] == 0

    async def test_delete_wrong_path_returns_404(self) -> None:
        resp = await self.client.request("DELETE", "/debug/webhook/wrong-path")
        assert resp.status == 404

    async def test_payload_cap_evicts_oldest(self) -> None:
        # MAX_DEBUG_WEBHOOK_PAYLOADS=3
        for i in range(5):
            await self.client.request(
                "POST", "/debug/webhook/secret-path", json={"n": i}
            )

        resp = await self.client.request("GET", "/debug/webhook/secret-path")
        data = await resp.json()
        assert data["count"] == 3
        # Oldest (0, 1) evicted; remaining are 2, 3, 4
        assert data["payloads"][0]["payload"]["n"] == 2
        assert data["payloads"][2]["payload"]["n"] == 4

    async def test_post_non_json_body(self) -> None:
        resp = await self.client.request(
            "POST",
            "/debug/webhook/secret-path",
            data=b"plain text body",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["payload"] == "plain text body"

    async def test_received_at_present(self) -> None:
        await self.client.request("POST", "/debug/webhook/secret-path", json={"x": 1})
        resp = await self.client.request("GET", "/debug/webhook/secret-path")
        data = await resp.json()
        assert "received_at" in data["payloads"][0]


if __name__ == "__main__":
    unittest.main()
