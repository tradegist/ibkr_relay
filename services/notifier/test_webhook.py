"""Unit tests for WebhookNotifier."""

import hashlib
import hmac as hmac_mod
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from notifier.webhook import WebhookNotifier


class _SamplePayload(BaseModel):
    symbol: str
    quantity: int


class TestWebhookNotifier:
    def test_dry_run_no_url(self) -> None:
        """No URL → logs payload, no HTTP call."""
        env = {"DEBUG_WEBHOOK_PATH": "test", "WEBHOOK_SECRET": "s"}
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier()
        # Force empty URL to exercise dry-run path
        notifier._url = ""
        notifier.send(_SamplePayload(symbol="AAPL", quantity=1))

    @patch("notifier.webhook.httpx.post")
    def test_sends_with_signature(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        secret = "test-secret"
        env = {
            "TARGET_WEBHOOK_URL": "https://example.com/hook",
            "WEBHOOK_SECRET": secret,
        }
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier()

        payload = _SamplePayload(symbol="AAPL", quantity=1)
        notifier.send(payload)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs["headers"]
        body = call_kwargs.kwargs["content"]

        expected_sig = hmac_mod.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        assert headers["X-Signature-256"] == f"sha256={expected_sig}"
        assert headers["Content-Type"] == "application/json"

    @patch("notifier.webhook.httpx.post")
    def test_custom_header_sent(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        env = {
            "TARGET_WEBHOOK_URL": "https://example.com/hook",
            "WEBHOOK_SECRET": "s",
            "WEBHOOK_HEADER_NAME": "X-Custom",
            "WEBHOOK_HEADER_VALUE": "my-value",
        }
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier()

        notifier.send(_SamplePayload(symbol="AAPL", quantity=1))

        headers = mock_post.call_args.kwargs["headers"]
        assert headers["X-Custom"] == "my-value"

    @patch("notifier.webhook.httpx.post")
    def test_http_error_does_not_raise(self, mock_post: MagicMock) -> None:
        """Webhook delivery failure is logged, not raised."""
        import httpx

        mock_post.side_effect = httpx.HTTPError("connection refused")
        env = {
            "TARGET_WEBHOOK_URL": "https://example.com/hook",
            "WEBHOOK_SECRET": "s",
        }
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier()

        notifier.send(_SamplePayload(symbol="AAPL", quantity=1))

    @patch("notifier.webhook.httpx.post")
    def test_suffix_reads_suffixed_vars(self, mock_post: MagicMock) -> None:
        """Suffix=_2 reads TARGET_WEBHOOK_URL_2, etc."""
        mock_post.return_value = MagicMock(status_code=200)
        env = {
            "TARGET_WEBHOOK_URL_2": "https://example.com/hook2",
            "WEBHOOK_SECRET_2": "secret2",
        }
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier(suffix="_2")

        notifier.send(_SamplePayload(symbol="GOOG", quantity=5))

        mock_post.assert_called_once()
        assert mock_post.call_args.kwargs["content"]  # body was sent

    def test_required_env_vars(self) -> None:
        assert "TARGET_WEBHOOK_URL" in WebhookNotifier.required_env_vars()
        assert "WEBHOOK_SECRET" in WebhookNotifier.required_env_vars()


class TestResolveWebhookUrl:
    def test_debug_path_overrides_target_url(self) -> None:
        env = {"DEBUG_WEBHOOK_PATH": "abc123", "TARGET_WEBHOOK_URL": "https://original.com", "WEBHOOK_SECRET": "s"}
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier()
        assert notifier._url == "http://ibkr-debug:9000/debug/webhook/abc123"

    def test_no_debug_path_uses_target_url(self) -> None:
        env = {"TARGET_WEBHOOK_URL": "https://original.com/hook", "WEBHOOK_SECRET": "s"}
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier()
        assert notifier._url == "https://original.com/hook"

    def test_blank_debug_path_uses_target_url(self) -> None:
        env = {"DEBUG_WEBHOOK_PATH": "  ", "TARGET_WEBHOOK_URL": "https://keep.com", "WEBHOOK_SECRET": "s"}
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier()
        assert notifier._url == "https://keep.com"


class TestValidation:
    def test_missing_required_vars_exits(self) -> None:
        """Constructor raises SystemExit when required env vars are missing."""
        with patch.dict("os.environ", {}, clear=True), \
             pytest.raises(SystemExit):
            WebhookNotifier()

    def test_missing_secret_exits(self) -> None:
        """WEBHOOK_SECRET is required even when DEBUG_WEBHOOK_PATH is set."""
        env = {"DEBUG_WEBHOOK_PATH": "abc123"}
        with patch.dict("os.environ", env, clear=True), \
             pytest.raises(SystemExit):
            WebhookNotifier()

    def test_debug_path_skips_target_url_validation(self) -> None:
        """TARGET_WEBHOOK_URL is not required when DEBUG_WEBHOOK_PATH is set."""
        env = {"DEBUG_WEBHOOK_PATH": "abc123", "WEBHOOK_SECRET": "s"}
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier()
        assert "ibkr-debug" in notifier._url

    def test_missing_target_url_without_debug_exits(self) -> None:
        """TARGET_WEBHOOK_URL is required when DEBUG_WEBHOOK_PATH is not set."""
        env = {"WEBHOOK_SECRET": "s"}
        with patch.dict("os.environ", env, clear=True), \
             pytest.raises(SystemExit):
            WebhookNotifier()

    def test_debug_path_ignores_suffix(self) -> None:
        """DEBUG_WEBHOOK_PATH has no suffix — all instances share the same debug inbox."""
        env = {"DEBUG_WEBHOOK_PATH": "xyz", "TARGET_WEBHOOK_URL_2": "https://other.com", "WEBHOOK_SECRET_2": "s"}
        with patch.dict("os.environ", env, clear=True):
            notifier = WebhookNotifier(suffix="_2")
        assert notifier._url == "http://ibkr-debug:9000/debug/webhook/xyz"
