"""Helpers for redacting sensitive data before logging or alerting."""

from urllib.parse import urlparse


def redact_url(url: str) -> str:
    """Redact likely-sensitive parts of a URL for safe inclusion in logs/alerts.

    URLs commonly embed secrets in the last path segment (Slack, Discord
    webhook tokens) or the query string (``?token=...``).  Drops the query
    and fragment entirely and masks the last non-empty path segment.  Host
    and leading path segments are kept so the operator can still identify
    which destination the URL points to.

    Returns the input unchanged when it does not parse as a URL (e.g. a
    sentinel like ``"<unknown>"`` or an empty string), so callers can pass
    arbitrary ``getattr(..., default)`` values without pre-checking.
    """
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url
        parts = (parsed.path or "").split("/")
        for i in range(len(parts) - 1, -1, -1):
            if parts[i]:
                parts[i] = "***"
                break
        return f"{parsed.scheme}://{parsed.netloc}{'/'.join(parts)}"
    except Exception:
        return "<redacted>"
