"""Tests for KrakenClient.get_ws_token validation."""

import threading
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


class TestNonceMonotonic(unittest.TestCase):
    """_next_nonce must produce a strictly increasing sequence even under contention."""

    def test_consecutive_calls_strictly_increase(self) -> None:
        client = _make_client()
        previous = client._next_nonce()
        for _ in range(1000):
            current = client._next_nonce()
            self.assertGreater(current, previous)
            previous = current

    def test_concurrent_threads_produce_unique_nonces_no_duplicates(self) -> None:
        client = _make_client()
        results: list[int] = []
        results_lock = threading.Lock()

        def worker() -> None:
            local: list[int] = []
            for _ in range(200):
                # Mirror production call ordering: _request acquires the
                # same lock around _next_nonce, so two threads cannot
                # observe an interleaved nonce.
                with client._request_lock:
                    local.append(client._next_nonce())
            with results_lock:
                results.extend(local)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 8 * 200)
        self.assertEqual(len(set(results)), len(results))
