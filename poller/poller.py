"""IBKR Flex Poller — polls Trade Confirmation Flex Queries and fires webhooks."""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("poller")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FLEX_TOKEN = os.environ.get("IBKR_FLEX_TOKEN", "")
FLEX_QUERY_ID = os.environ.get("IBKR_FLEX_QUERY_ID", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "600"))
TARGET_WEBHOOK_URL = os.environ.get("TARGET_WEBHOOK_URL", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
DB_PATH = os.environ.get("DB_PATH", "/data/poller.db")

FLEX_BASE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
USER_AGENT = "ibkr-relay/1.0"


# ---------------------------------------------------------------------------
# SQLite — deduplication of processed fills
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_fills (
            exec_id TEXT PRIMARY KEY,
            processed_at TEXT DEFAULT (datetime('now')),
            payload TEXT
        )
    """)
    conn.commit()
    return conn


def is_processed(conn, exec_id):
    return conn.execute(
        "SELECT 1 FROM processed_fills WHERE exec_id = ?", (exec_id,)
    ).fetchone() is not None


def mark_processed(conn, exec_id, payload):
    conn.execute(
        "INSERT OR IGNORE INTO processed_fills (exec_id, payload) VALUES (?, ?)",
        (exec_id, json.dumps(payload, default=str)),
    )
    conn.commit()


def prune_old(conn, days=30):
    conn.execute(
        "DELETE FROM processed_fills WHERE processed_at < datetime('now', ?)",
        (f"-{days} days",),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Webhook delivery
# ---------------------------------------------------------------------------
def send_webhook(payload: dict) -> None:
    body = json.dumps(payload, default=str, indent=2)

    if not TARGET_WEBHOOK_URL:
        log.info("Webhook payload (dry-run):\n%s", body)
        return

    signature = hmac.new(
        WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    try:
        resp = httpx.post(
            TARGET_WEBHOOK_URL,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-256": f"sha256={signature}",
            },
            timeout=10.0,
        )
        log.info("Webhook sent — status %d", resp.status_code)
    except httpx.HTTPError as exc:
        log.error("Webhook delivery failed: %s", exc)


# ---------------------------------------------------------------------------
# Flex Web Service
# ---------------------------------------------------------------------------
def fetch_flex_report():
    """Two-step Flex Web Service: SendRequest -> GetStatement."""
    headers = {"User-Agent": USER_AGENT}

    # Step 1: request report generation
    resp = httpx.get(
        f"{FLEX_BASE}/SendRequest",
        params={"t": FLEX_TOKEN, "q": FLEX_QUERY_ID, "v": "3"},
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    if root.findtext("Status") != "Success":
        code = root.findtext("ErrorCode", "?")
        msg = root.findtext("ErrorMessage", "Unknown error")
        log.error("SendRequest failed: [%s] %s", code, msg)
        return None

    ref_code = root.findtext("ReferenceCode")
    log.debug("SendRequest OK — ref=%s, waiting for report...", ref_code)

    # Step 2: poll for the generated report
    for wait in (5, 10, 15, 30):
        time.sleep(wait)
        resp = httpx.get(
            f"{FLEX_BASE}/GetStatement",
            params={"t": FLEX_TOKEN, "q": ref_code, "v": "3"},
            headers=headers,
            timeout=60.0,
        )
        resp.raise_for_status()

        # Error responses are wrapped in <FlexStatementResponse>
        if resp.text.strip().startswith("<FlexStatementResponse"):
            err_root = ET.fromstring(resp.text)
            err_code = err_root.findtext("ErrorCode", "")
            if err_code == "1019":  # generation in progress
                log.debug("Report still generating, retrying...")
                continue
            msg = err_root.findtext("ErrorMessage", "Unknown error")
            log.error("GetStatement failed: [%s] %s", err_code, msg)
            return None

        return resp.text

    log.error("Report generation timed out after retries")
    return None


def parse_trades(xml_text):
    """Parse Flex Query XML for trade records."""
    root = ET.fromstring(xml_text)
    trades = []
    seen = set()

    # Trade Confirmation queries use <TradeConfirmation>,
    # Activity queries use <Trade>. Check both.
    for tag in ("TradeConfirmation", "Trade"):
        for el in root.iter(tag):
            exec_id = el.get("transactionID", "") or el.get("ibExecID", "")
            if not exec_id or exec_id in seen:
                continue
            seen.add(exec_id)

            try:
                qty = float(el.get("quantity", 0))
            except (ValueError, TypeError):
                qty = 0.0
            try:
                price = float(el.get("price", 0))
            except (ValueError, TypeError):
                price = 0.0
            try:
                commission = float(el.get("commission", 0))
            except (ValueError, TypeError):
                commission = 0.0

            trades.append({
                "event": "fill",
                "symbol": el.get("symbol", ""),
                "secType": el.get("assetCategory", ""),
                "exchange": el.get("exchange", ""),
                "action": el.get("buySell", ""),
                "quantity": qty,
                "price": price,
                "tradeDate": el.get("tradeDate", ""),
                "tradeTime": el.get("dateTime", ""),
                "orderId": el.get("orderID", ""),
                "execId": exec_id,
                "account": el.get("accountId", ""),
                "commission": commission,
                "currency": el.get("currency", ""),
            })

    return trades


# ---------------------------------------------------------------------------
# Poll cycle
# ---------------------------------------------------------------------------
def poll_once(conn=None):
    """Run a single poll. Returns number of new fills processed."""
    close_conn = conn is None
    if close_conn:
        conn = init_db()

    try:
        log.info("Polling Flex Web Service...")
        xml_text = fetch_flex_report()
        if xml_text is None:
            return 0

        trades = parse_trades(xml_text)
        log.info("Received %d trade(s) from Flex report", len(trades))

        new_count = 0
        for trade in trades:
            if is_processed(conn, trade["execId"]):
                continue

            log.info(
                "New fill: %s %s %s @ %s",
                trade["action"], trade["quantity"],
                trade["symbol"], trade["price"],
            )
            send_webhook(trade)
            mark_processed(conn, trade["execId"], trade)
            new_count += 1

        if new_count == 0:
            log.info("No new fills")
        else:
            log.info("Processed %d new fill(s)", new_count)

        return new_count
    finally:
        if close_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def main_loop():
    """Continuous polling loop."""
    if not FLEX_TOKEN or not FLEX_QUERY_ID:
        log.error("IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID must be set")
        raise SystemExit(1)

    log.info("IBKR Flex Poller starting (poll every %ds)", POLL_INTERVAL)
    if not TARGET_WEBHOOK_URL:
        log.info("No TARGET_WEBHOOK_URL — running in dry-run mode")

    conn = init_db()
    prune_old(conn)

    while True:
        try:
            poll_once(conn)
        except Exception:
            log.exception("Poll cycle failed")

        log.debug("Next poll in %ds", POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)


def main_once():
    """Single on-demand poll, then exit."""
    if not FLEX_TOKEN or not FLEX_QUERY_ID:
        log.error("IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID must be set")
        raise SystemExit(1)

    conn = init_db()
    n = poll_once(conn)
    conn.close()
    print(f"Done — {n} new fill(s) processed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        main_once()
    else:
        main_loop()
