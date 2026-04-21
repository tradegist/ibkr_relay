"""Canonical timestamp format for all Fill / Trade timestamps.

Every ``Fill.timestamp`` reaching the engine MUST be in the canonical form:

    YYYY-MM-DDTHH:MM:SS

- Always UTC.
- No ``Z`` suffix, no ``+00:00`` suffix, no fractional seconds.
- Lexicographic order == chronological order (used by the poll watermark).

This module is broker-agnostic. :func:`normalize_timestamp` only accepts
**ISO-8601** input. Each relay adapter is responsible for converting its
broker's native timestamp format (IBKR Flex, IBKR bridge, …) into
ISO-8601 before calling this helper — keeping broker-specific parsing
colocated with the relay that owns it.
"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def normalize_timestamp(raw: str, *, assume_tz: tzinfo | None = None) -> str:
    """Return *raw* (ISO-8601) reformatted as canonical ``YYYY-MM-DDTHH:MM:SS`` UTC.

    - Tz-aware inputs are converted to UTC (``assume_tz`` ignored).
    - Tz-naive inputs are interpreted in ``assume_tz`` (default: UTC).
    - Fractional seconds are dropped.

    Raises ``ValueError`` when *raw* is empty or not valid ISO-8601.
    """
    if not raw:
        raise ValueError("empty timestamp")

    # Python 3.11's fromisoformat rejects "Z"; 3.12+ accepts it. Normalise
    # up-front so behaviour is version-independent.
    iso_candidate = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(iso_candidate)
    except ValueError as exc:
        raise ValueError(f"Not a valid ISO-8601 timestamp: {raw!r}") from exc

    tz = assume_tz if assume_tz is not None else UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    dt_utc = dt.astimezone(UTC).replace(microsecond=0)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S")


def parse_timezone(name: str) -> ZoneInfo:
    """Return a ``ZoneInfo`` for *name*, or raise ``ValueError``.

    Small wrapper so callers can convert ``ZoneInfoNotFoundError`` into
    a message they control (e.g. ``SystemExit`` at boot).
    """
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone {name!r}") from exc
