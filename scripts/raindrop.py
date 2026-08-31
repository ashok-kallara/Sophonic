#!/usr/bin/env python3
"""Raindrop.io bookmarks (read-only) → JSON.

    uv run python scripts/raindrop.py check-auth
    uv run python scripts/raindrop.py collections
    uv run python scripts/raindrop.py list --days 30
    uv run python scripts/raindrop.py list --since 2026-08-01 --until 2026-08-30
    uv run python scripts/raindrop.py list --collection Reading --limit 20
    uv run python scripts/raindrop.py list --tag ai --tag infra --type article
    uv run python scripts/raindrop.py list --search "prompt caching"

`list` defaults to the last 30 days, newest first, across all collections. Requires the
RAINDROP_TOKEN secret (a Raindrop.io "test token" — see the `raindrop` skill's Auth
section).
"""

from __future__ import annotations

import argparse
from datetime import date

from _common import run


def main() -> None:
    p = argparse.ArgumentParser(description="Raindrop.io bookmarks (read-only).")
    sub = p.add_subparsers(dest="action", required=True)

    sub.add_parser("check-auth", help="Probe whether the token is valid")
    sub.add_parser("collections", help="List collections (id, title, path, count)")

    lst = sub.add_parser("list", help="List bookmarks in a date window")
    lst.add_argument("--days", type=int, default=30, help="Lookback window (default 30)")
    lst.add_argument("--since", help="ISO date; overrides --days")
    lst.add_argument("--until", help="ISO date (default today)")
    lst.add_argument("--collection", help="Collection id or name/path")
    lst.add_argument("--tag", action="append", dest="tags", help="Repeatable tag filter")
    lst.add_argument("--search", help="Raindrop full-text search query")
    lst.add_argument("--type", dest="item_type",
                      help="Filter by raindrop type, e.g. article, link, image")
    lst.add_argument("--limit", type=int, help="Cap the number of items returned")

    args = p.parse_args()

    from sophonic import raindrop

    if args.action == "check-auth":
        run(raindrop.check_auth)
    elif args.action == "collections":
        run(raindrop.collections)
    else:
        run(
            raindrop.bookmarks,
            days=args.days,
            since=date.fromisoformat(args.since) if args.since else None,
            until=date.fromisoformat(args.until) if args.until else None,
            collection=args.collection,
            tags=args.tags,
            search=args.search,
            item_type=args.item_type,
            limit=args.limit,
        )


if __name__ == "__main__":
    main()
