#!/usr/bin/env python3
"""Gmail (read-only) → JSON.

    uv run python scripts/gmail.py unread --max 20
    uv run python scripts/gmail.py search --query "is:unread from:boss" --max 10
    uv run python scripts/gmail.py thread --thread-id 18f2a...
"""

from __future__ import annotations

import argparse

from _common import run


def main() -> None:
    p = argparse.ArgumentParser(description="Gmail (read-only).")
    sub = p.add_subparsers(dest="action", required=True)

    u = sub.add_parser("unread", help="Recent unread messages")
    u.add_argument("--max", type=int, default=20)

    s = sub.add_parser("search", help="Search with Gmail query syntax")
    s.add_argument("--query", required=True)
    s.add_argument("--max", type=int, default=20)

    t = sub.add_parser("thread", help="All messages in a thread, with bodies")
    t.add_argument("--thread-id", required=True)

    args = p.parse_args()

    from sophonic import gmail

    if args.action == "unread":
        run(gmail.unread, max=args.max)
    elif args.action == "search":
        run(gmail.search, args.query, max=args.max)
    else:
        run(gmail.thread, args.thread_id)


if __name__ == "__main__":
    main()
