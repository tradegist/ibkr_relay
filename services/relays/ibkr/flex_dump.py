"""CLI entrypoint: fetch a live IBKR Flex report and write it to disk.

Run as:  python -m relays.ibkr.flex_dump --token TOKEN --query-id ID [--dump PATH]
"""

import argparse
import logging
import sys
from pathlib import Path

from relays.ibkr.flex_fetch import RedactTokenFilter, fetch_flex_report

_DEFAULT_DUMP_PATH = "services/relays/ibkr/fixtures/raw.xml"

log = logging.getLogger("relays.ibkr.flex_dump")


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump an IBKR Flex report (Activity or Trade Confirmation) to disk.",
    )
    parser.add_argument("--token", required=True, help="IBKR Flex token.")
    parser.add_argument("--query-id", required=True, dest="query_id", help="IBKR Flex query ID.")
    parser.add_argument(
        "--dump", metavar="PATH", default=_DEFAULT_DUMP_PATH,
        help=f"Output file path (default: {_DEFAULT_DUMP_PATH}).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger().addFilter(RedactTokenFilter())

    xml = fetch_flex_report(flex_token=args.token, flex_query_id=args.query_id)
    if xml is None:
        sys.exit("Flex fetch failed — see log output above")

    path = Path(args.dump)
    path.write_text(xml)
    log.info("Wrote %d bytes to %s", len(xml), path)


if __name__ == "__main__":
    _main()
