#!/usr/bin/env python3
"""Google Tasks (read-only) → JSON.

    uv run python scripts/gtasks.py list --max-lists 20 --max-tasks 100

Prints a list of open tasks, or a {"needs_auth": true, "run": "..."} stub if the
signed-in token lacks the tasks.readonly scope.
"""

from __future__ import annotations

import argparse

from _common import run


def main() -> None:
    p = argparse.ArgumentParser(description="Google Tasks open items (read-only).")
    sub = p.add_subparsers(dest="action", required=True)
    ls = sub.add_parser("list", help="Open tasks across all lists")
    ls.add_argument("--max-lists", type=int, default=20)
    ls.add_argument("--max-tasks", type=int, default=100)
    args = p.parse_args()

    from sophonic import gtasks

    run(gtasks.list_open_tasks, max_lists=args.max_lists, max_tasks=args.max_tasks)


if __name__ == "__main__":
    main()
