"""IBKR-specific timestamp → ISO-8601 conversion.

Two native formats arrive from IBKR:

* **Flex XML** (``dateTime`` attribute): ``YYYYMMDD;HHMMSS`` e.g. ``20250403;153000``
* **ib_async bridge** (``Execution.time``): ``YYYYMMDD-HH:MM:SS`` e.g. ``20260411-10:30:00``

Both are naive (no timezone). Each function here turns one of them into a
naive ISO-8601 string the shared :func:`shared.normalize_timestamp` layer
can finish — applying ``IBKR_ACCOUNT_TIMEZONE`` and producing the
canonical UTC form.

Having the format knowledge here (rather than in ``shared/time_format.py``)
keeps ``time_format`` broker-agnostic — every new relay's quirks stay in
its own package.
"""

from datetime import datetime


def flex_to_iso(raw: str) -> str:
    """Convert a Flex XML ``dateTime`` attribute to naive ISO-8601.

    Raises ``ValueError`` when *raw* does not match the expected form.
    """
    try:
        dt = datetime.strptime(raw, "%Y%m%d;%H%M%S")
    except ValueError as exc:
        raise ValueError(
            f"Not a valid IBKR Flex dateTime (expected YYYYMMDD;HHMMSS): {raw!r}"
        ) from exc
    return dt.isoformat(timespec="seconds")


def bridge_to_iso(raw: str) -> str:
    """Convert an ib_async bridge ``Execution.time`` to naive ISO-8601.

    Raises ``ValueError`` when *raw* does not match the expected form.
    """
    try:
        dt = datetime.strptime(raw, "%Y%m%d-%H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            f"Not a valid IBKR bridge time (expected YYYYMMDD-HH:MM:SS): {raw!r}"
        ) from exc
    return dt.isoformat(timespec="seconds")
