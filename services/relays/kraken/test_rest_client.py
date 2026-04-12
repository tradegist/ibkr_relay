"""Tests for KrakenClient.get_ws_token validation."""

import unittest
from unittest.mock import patch

from .rest_client import KrakenClient

# base64.b64encode(b"test-secret") -> "dGVzdC1zZWNyZXQ="
_KEY = "test-api-key"
_SECRET = "dGVzdC1zZWNyZXQ="


def _make_client() -> KrakenClient:
    return KrakenClient(api_key=_KEY, api_secret=_SECRET)


class TestGetWsTokenValidation(unittest.TestCase):
    """get_ws_token must reject responses that lack a valid token."""

    def _call_with_result(self, result: object) -> str:
        client = _make_client()
        with patch.object(client, "_request", return_value=result):
            return client.get_ws_token()

    def test_valid_token_returned(self) -> None:
        token = self._call_with_result({"token": "abc123"})
        self.assertEqual(token, "abc123")

    def test_missing_token_key_raises(self) -> None:
        with self.assertRaises(RuntimeError) as cm:
            self._call_with_result({"expires": 900})
        self.assertIn("unexpected payload", str(cm.exception))

    def test_result_not_a_dict_raises(self) -> None:
        with self.assertRaises(RuntimeError) as cm:
            self._call_with_result(["token", "abc123"])
        self.assertIn("unexpected payload", str(cm.exception))

    def test_result_none_raises(self) -> None:
        with self.assertRaises(RuntimeError) as cm:
            self._call_with_result(None)
        self.assertIn("unexpected payload", str(cm.exception))

    def test_token_empty_string_raises(self) -> None:
        with self.assertRaises(RuntimeError) as cm:
            self._call_with_result({"token": ""})
        self.assertIn("invalid token value", str(cm.exception))

    def test_token_not_a_string_raises(self) -> None:
        with self.assertRaises(RuntimeError) as cm:
            self._call_with_result({"token": 12345})
        self.assertIn("invalid token value", str(cm.exception))
