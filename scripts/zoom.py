#!/usr/bin/env python3
"""Zoom AI Companion meeting notes (read-only) → JSON.

    uv run python scripts/zoom.py check-auth
    uv run python scripts/zoom.py notes --limit 20
    uv run python scripts/zoom.py note --id <doc_id>
    uv run python scripts/zoom.py action-items --days 1 --owner "Jane"

`action-items` returns extracted items grouped by meeting; it does NOT write the vault
— the start-my-day/zoom skill dedupes against today's note and writes the tasks itself.
On missing/expired cookies the result carries {"needs_auth": true, "run": "..."}.
"""

from __future__ import annotations

import argparse

from _common import run


def main() -> None:
    p = argparse.ArgumentParser(description="Zoom AI meeting notes (read-only).")
    sub = p.add_subparsers(dest="action", required=True)

    sub.add_parser("check-auth", help="Probe whether the pasted Zoom session is still valid")

    n = sub.add_parser("notes", help="List recent AI meeting notes")
    n.add_argument("--limit", type=int, default=20)

    one = sub.add_parser("note", help="Fetch one note's content by doc id")
    one.add_argument("--id", required=True)

    ai = sub.add_parser("action-items", help="Extract action items in a date window")
    ai.add_argument("--on", help="Single day (ISO or natural, e.g. 'yesterday')")
    ai.add_argument("--since", help="Range start (ISO or natural)")
    ai.add_argument("--until", help="Range end (ISO or natural)")
    ai.add_argument("--days", type=int, help="Last N days including today")
    ai.add_argument("--owner", help="Keep only items whose text contains this substring")
    ai.add_argument("--limit", type=int, default=50)

    args = p.parse_args()

    from sophonic import zoom

    if args.action == "check-auth":
        run(zoom.check_auth)
    elif args.action == "notes":
        run(zoom.notes, args.limit)
    elif args.action == "note":
        run(zoom.note, args.id)
    else:
        run(
            zoom.action_items,
            on=args.on, since=args.since, until=args.until,
            days=args.days, owner=args.owner, limit=args.limit,
        )


if __name__ == "__main__":
    main()
