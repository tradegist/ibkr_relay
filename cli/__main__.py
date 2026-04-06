#!/usr/bin/env python3
import argparse
import importlib
import sys

import cli  # triggers set_config()
from cli.core import CORE_MODULES, register_parsers

# Project-specific command → module mapping
_PROJECT_MODULES: dict[str, str] = {
    "poll": "cli.poll",
    "order": "cli.order",
    "test-webhook": "cli.test_webhook",
}


def main():
    parser = argparse.ArgumentParser(
        description="IBKR Webhook Relay CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # ── Core commands (shared across projects) ──
    register_parsers(sub)

    # ── Project-specific commands ──
    p = sub.add_parser("poll", help="Trigger an immediate Flex poll")
    p.add_argument("poller", nargs="?", default="1", choices=["1", "2"],
                   help="Which poller (default: 1)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Run poll via SSH to see full poller logs")
    p.add_argument("--debug", action="store_true",
                   help="Dump raw Flex XML (implies -v)")
    p.add_argument("--replay", type=int, metavar="N",
                   help="Resend N trades even if already processed (for testing)")

    p = sub.add_parser("test-webhook", help="Send sample trades to webhook endpoint")
    p.add_argument("poller", nargs="?", default="1", choices=["1", "2"],
                   help="Which poller's webhook URL (default: 1)")

    p = sub.add_parser("order", help="Place a stock order")
    p.add_argument("quantity", type=int, help="Positive=BUY, negative=SELL")
    p.add_argument("symbol", help="Ticker symbol")
    p.add_argument("order_type", choices=["MKT", "LMT", "mkt", "lmt"],
                   help="Order type")
    p.add_argument("limit_price", nargs="?", type=float,
                   help="Limit price (required for LMT)")
    p.add_argument("currency", nargs="?", default="USD",
                   help="Currency (default: USD)")
    p.add_argument("exchange", nargs="?", default="SMART",
                   help="Exchange (default: SMART)")
    p.add_argument("--tif", default="DAY",
                   choices=["DAY", "GTC", "IOC", "GTD", "OPG", "FOK", "DTC"],
                   help="Time in force (default: DAY)")
    p.add_argument("--outside-rth", action="store_true",
                   help="Allow execution outside regular trading hours")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    modules = {**CORE_MODULES, **_PROJECT_MODULES}
    module = importlib.import_module(modules[args.command])
    module.run(args)


if __name__ == "__main__":
    main()
