#!/usr/bin/env python3
"""Google Drive open comments mentioning you (read-only) → JSON.

    uv run python scripts/gdrive.py mentioned-comments
    uv run python scripts/gdrive.py mentioned-comments --days 7 --max-files 20
    uv run python scripts/gdrive.py mentioned-comments --all

Prints a list of unresolved comments where you are @mentioned or assigned, or a
{"needs_auth": true, "run": "..."} stub if the token lacks the drive.readonly scope.

`--all` drops the day filter and paginates through every Doc/Sheet you can see (up to
--max-files, default 2000 in this mode) — a full-Drive scan for when a day-bounded pass
finds nothing. It costs one extra API call per file, so it's slower; never trigger it
without telling the user first.
"""

from __future__ import annotations

import argparse

from _common import run


def main() -> None:
    p = argparse.ArgumentParser(description="Google Drive open comments mentioning you.")
    sub = p.add_subparsers(dest="action", required=True)
    mc = sub.add_parser(
        "mentioned-comments",
        help="Unresolved comments in Docs/Sheets where you are @mentioned or assigned",
    )
    mc.add_argument("--days", type=int, default=30, help="Look back this many days (default 30); ignored if --all is set")
    mc.add_argument("--max-files", type=int, default=None, help="Max files to check (default 50, or 2000 with --all)")
    mc.add_argument("--all", action="store_true", help="Full scan: ignore --days, paginate through every Doc/Sheet you can access")
    args = p.parse_args()

    from sophonic import gdrive

    days = None if args.all else args.days
    max_files = args.max_files if args.max_files is not None else (2000 if args.all else 50)
    run(gdrive.list_mentioned_comments, days=days, max_files=max_files)


if __name__ == "__main__":
    main()
