"""Tests for the URL redaction helper."""

from shared.redact import redact_url


class TestRedactUrl:
    def test_masks_last_path_segment(self) -> None:
        assert (
            redact_url("https://discord.com/api/webhooks/123/SECRET_TOKEN")
            == "https://discord.com/api/webhooks/123/***"
        )

    def test_masks_slack_style_token(self) -> None:
        assert (
            redact_url("https://hooks.slack.com/services/T0/B0/SECRET")
            == "https://hooks.slack.com/services/T0/B0/***"
        )

    def test_drops_query_string(self) -> None:
        assert (
            redact_url("https://api.example.com/webhook?token=SECRET")
            == "https://api.example.com/***"
        )

    def test_drops_fragment(self) -> None:
        assert (
            redact_url("https://api.example.com/webhook/abc#frag")
            == "https://api.example.com/webhook/***"
        )

    def test_drops_query_and_fragment(self) -> None:
        assert (
            redact_url("https://api.example.com/webhook/abc?k=v#frag")
            == "https://api.example.com/webhook/***"
        )

    def test_handles_trailing_slash(self) -> None:
        # Trailing slash leaves the last segment empty — mask the one before.
        assert (
            redact_url("https://api.example.com/webhook/abc/")
            == "https://api.example.com/webhook/***/"
        )

    def test_root_path(self) -> None:
        # No path segment to mask — return host as-is.
        assert redact_url("https://example.com") == "https://example.com"

    def test_root_path_with_slash(self) -> None:
        assert redact_url("https://example.com/") == "https://example.com/"

    def test_passes_through_non_url_sentinel(self) -> None:
        assert redact_url("<unknown>") == "<unknown>"

    def test_passes_through_empty_string(self) -> None:
        assert redact_url("") == ""

    def test_passes_through_plain_text(self) -> None:
        # No scheme / netloc → return as-is, don't mangle.
        assert redact_url("not a url") == "not a url"

    def test_preserves_port(self) -> None:
        assert (
            redact_url("https://api.example.com:8443/webhook/SECRET")
            == "https://api.example.com:8443/webhook/***"
        )

    def test_http_scheme(self) -> None:
        assert (
            redact_url("http://internal.local/hook/abc")
            == "http://internal.local/hook/***"
        )
