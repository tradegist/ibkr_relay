"""E2E tests — verify the listener fires webhooks on trade events.

The listener subscribes to ib_async execDetailsEvent and commissionReportEvent.
When the remote-client places a paper order, ib_async emits both events.
Each event fires a webhook to the debug inbox container (ibkr-debug).

NOTE: These tests only produce webhooks when the market is open and orders
actually fill.  When the market is closed, orders stay PreSubmitted and no
execution events are emitted.  Tests skip gracefully in that case.
"""

import hashlib
import hmac
import time
from collections.abc import Generator
from datetime import datetime
from typing import TypedDict

import httpx
import pytest

from shared import WebhookPayloadTrades

WEBHOOK_SECRET = "test-webhook-secret"
_DEBUG_INBOX_PATH = "/debug/webhook/test-debug-path"


# ── Typed webhook entry ──────────────────────────────────────────────────


class _WebhookEntry(TypedDict):
    """Single entry fetched from the debug webhook inbox."""

    body: WebhookPayloadTrades
    signature: str
    received_at: str  # ISO timestamp


# ── Debug inbox helpers ──────────────────────────────────────────────────


def _fetch_inbox(client: httpx.Client) -> list[_WebhookEntry]:
    """Fetch and parse all entries from the debug webhook inbox."""
    resp = client.get(_DEBUG_INBOX_PATH)
    resp.raise_for_status()
    entries: list[_WebhookEntry] = []
    for raw in resp.json()["payloads"]:
        entries.append({
            "body": WebhookPayloadTrades.model_validate(raw["payload"]),
            "signature": raw["headers"].get("X-Signature-256", ""),
            "received_at": raw["received_at"],
        })
    return entries


def _clear_inbox(client: httpx.Client) -> None:
    """Clear all entries from the debug webhook inbox."""
    resp = client.delete(_DEBUG_INBOX_PATH)
    resp.raise_for_status()


@pytest.fixture(scope="module")
def debug_inbox() -> Generator[httpx.Client]:
    """HTTP client for the debug webhook inbox (ibkr-debug on port 15012)."""
    with httpx.Client(base_url="http://localhost:15012", timeout=10) as client:
        yield client


def _wait_for_fill(api: httpx.Client, order_id: int, timeout: float = 10) -> bool:
    """Return True if the order fills within timeout, False otherwise."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = api.get("/ibkr/trades")
        if resp.status_code == 200:
            for t in resp.json()["trades"]:
                if t["orderId"] == order_id and t["status"] == "Filled":
                    return True
        time.sleep(0.5)
    return False


def _poll_inbox(
    client: httpx.Client,
    *,
    min_count: int = 1,
    timeout: float = 15,
) -> list[_WebhookEntry]:
    """Poll the debug inbox until at least *min_count* entries appear."""
    deadline = time.monotonic() + timeout
    entries: list[_WebhookEntry] = []
    while time.monotonic() < deadline:
        entries = _fetch_inbox(client)
        if len(entries) >= min_count:
            return entries
        time.sleep(0.5)
    return entries


# ── Tests ────────────────────────────────────────────────────────────────


def test_listener_fires_on_market_order(
    api: httpx.Client, debug_inbox: httpx.Client,
) -> None:
    """Place MKT BUY → expect execDetailsEvent + commissionReportEvent webhooks.

    Skips when the market is closed (orders don't fill → no execution events).
    """
    _clear_inbox(debug_inbox)

    resp = api.post(
        "/ibkr/order",
        json={
            "contract": {"symbol": "AAPL"},
            "order": {"action": "BUY", "totalQuantity": 1, "orderType": "MKT"},
        },
    )
    assert resp.status_code == 200, resp.text

    order_id = resp.json()["orderId"]
    filled = _wait_for_fill(api, order_id, timeout=10)
    if not filled:
        pytest.skip("Market appears closed — order did not fill, no execution events expected")

    # Wait for at least 2 webhooks (exec + commission)
    entries = _poll_inbox(debug_inbox, min_count=2, timeout=15)
    assert len(entries) >= 2, f"Expected >= 2 webhooks, got {len(entries)}"

    # Verify payload structure
    for entry in entries:
        payload = entry["body"]
        assert len(payload.data) == 1

        trade = payload.data[0]
        assert trade.source in ("execDetailsEvent", "commissionReportEvent")
        assert trade.symbol == "AAPL"
        assert trade.side == "buy"

    # Both event types must be present
    sources = {e["body"].data[0].source for e in entries}
    assert "execDetailsEvent" in sources, f"Missing execDetailsEvent, got: {sources}"
    assert "commissionReportEvent" in sources, f"Missing commissionReportEvent, got: {sources}"


def test_webhook_hmac_signature(
    debug_inbox: httpx.Client,
) -> None:
    """Verify all received webhooks have valid HMAC-SHA256 signatures.

    Reconstructs the original body via Pydantic round-trip (the debug inbox
    stores parsed JSON, not raw bytes).
    """
    entries = _fetch_inbox(debug_inbox)
    if len(entries) == 0:
        pytest.skip("No webhooks received (market likely closed)")

    for entry in entries:
        # Reconstruct the body as the notifier produces it
        reconstructed = entry["body"].model_dump_json(indent=2).encode()
        expected = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode(), reconstructed, hashlib.sha256,
        ).hexdigest()
        assert hmac.compare_digest(entry["signature"], expected), (
            f"HMAC mismatch: got {entry['signature']!r}"
        )


def test_commission_report_has_commission(
    debug_inbox: httpx.Client,
) -> None:
    """The commissionReportEvent webhook should include fee > 0."""
    entries = _fetch_inbox(debug_inbox)
    commission_entries = [
        e for e in entries
        if e["body"].data[0].source == "commissionReportEvent"
    ]
    if len(commission_entries) == 0:
        pytest.skip("No commissionReportEvent webhooks received (market likely closed)")

    for entry in commission_entries:
        trade = entry["body"].data[0]
        assert trade.fee > 0, f"Expected fee > 0, got {trade.fee}"


def test_debounce_path_fires_webhook(
    api: httpx.Client, debug_inbox: httpx.Client,
) -> None:
    """With LISTENER_EVENT_DEBOUNCE_TIME=2000, commissionReportEvent goes through
    the debounce path: enqueue → timer → flush → aggregate → webhook.

    Verify the webhook arrives after at least ~2s (the debounce window) and
    contains the expected aggregated fields (execIds, fillCount).
    """
    _clear_inbox(debug_inbox)

    resp = api.post(
        "/ibkr/order",
        json={
            "contract": {"symbol": "AAPL"},
            "order": {"action": "BUY", "totalQuantity": 1, "orderType": "MKT"},
        },
    )
    assert resp.status_code == 200, resp.text

    order_id = resp.json()["orderId"]
    filled = _wait_for_fill(api, order_id, timeout=10)
    if not filled:
        pytest.skip("Market appears closed — order did not fill")

    # execDetailsEvent arrives immediately (no debounce) — filter by THIS order
    deadline = time.monotonic() + 5
    exec_events: list[_WebhookEntry] = []
    while time.monotonic() < deadline:
        entries = _fetch_inbox(debug_inbox)
        exec_events = [
            e for e in entries
            if e["body"].data[0].source == "execDetailsEvent"
            and str(e["body"].data[0].orderId) == str(order_id)
        ]
        if exec_events:
            break
        time.sleep(0.3)
    assert exec_events, "execDetailsEvent webhook never arrived"

    # commissionReportEvent should arrive after debounce (~2s window from fill)
    # Filter by THIS order's orderId to avoid picking up stale events from
    # prior tests whose debounced webhooks may arrive after our baseline.
    deadline = time.monotonic() + 10
    commission_event: _WebhookEntry | None = None
    while time.monotonic() < deadline:
        entries = _fetch_inbox(debug_inbox)
        for e in entries:
            t = e["body"].data[0]
            if (t.source == "commissionReportEvent"
                    and str(t.orderId) == str(order_id)):
                commission_event = e
                break
        if commission_event:
            break
        time.sleep(0.3)

    assert commission_event is not None, "commissionReportEvent webhook never arrived"

    # The debounce path produces aggregated fields
    trade = commission_event["body"].data[0]
    assert len(trade.execIds) >= 1
    assert trade.fillCount >= 1
    assert trade.symbol == "AAPL"
    assert trade.side == "buy"

    # Measure the gap between execDetailsEvent and commissionReportEvent arrival
    # times via ISO timestamps from the debug inbox.
    exec_arrived = datetime.fromisoformat(exec_events[0]["received_at"])
    comm_arrived = datetime.fromisoformat(commission_event["received_at"])
    gap = (comm_arrived - exec_arrived).total_seconds()
    assert gap >= 1.5, (
        f"commissionReportEvent arrived only {gap:.1f}s after execDetailsEvent, "
        "debounce path may not have been used (expected >= 1.5s for 2s debounce)"
    )
