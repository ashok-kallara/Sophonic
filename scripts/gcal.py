#!/usr/bin/env python3
"""Google Calendar (read-only) → JSON.

    uv run python scripts/gcal.py events-today
    uv run python scripts/gcal.py events-range --start 2026-08-01 --end 2026-08-07
"""

from __future__ import annotations

import argparse
from datetime import date

from _common import run


def main() -> None:
    p = argparse.ArgumentParser(description="Google Calendar events (read-only).")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("events-today", help="Today's events")
    r = sub.add_parser("events-range", help="Events between two ISO dates (inclusive)")
    r.add_argument("--start", required=True, help="ISO date, e.g. 2026-08-01")
    r.add_argument("--end", required=True, help="ISO date, e.g. 2026-08-07")
    args = p.parse_args()

    from sophonic import gcal

    if args.action == "events-today":
        run(gcal.events_today)
    else:
        run(gcal.events_range, date.fromisoformat(args.start), date.fromisoformat(args.end))


if __name__ == "__main__":
    main()
