#!/usr/bin/env python3
"""Google Drive open comments mentioning you (read-only) → JSON.

    uv run python scripts/gdrive.py mentioned-comments
    uv run python scripts/gdrive.py mentioned-comments --days 7 --max-files 20

Prints a list of unresolved comments where you are @mentioned or assigned, or a
{"needs_auth": true, "run": "..."} stub if the token lacks the drive.readonly scope.
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
    mc.add_argument("--days", type=int, default=30, help="Look back this many days (default 30)")
    mc.add_argument("--max-files", type=int, default=50, help="Max files to check (default 50)")
    args = p.parse_args()

    from sophonic import gdrive

    run(gdrive.list_mentioned_comments, days=args.days, max_files=args.max_files)


if __name__ == "__main__":
    main()
