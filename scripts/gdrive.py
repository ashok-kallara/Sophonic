#!/usr/bin/env python3
"""Google Drive comments and document/spreadsheet content (read-only) → JSON.

    uv run python scripts/gdrive.py mentioned-comments
    uv run python scripts/gdrive.py mentioned-comments --days 7 --max-files 20
    uv run python scripts/gdrive.py mentioned-comments --all
    uv run python scripts/gdrive.py search-content --query "Q3 budget"

`mentioned-comments` prints unresolved comments where you are @mentioned or assigned.
`--all` drops the day filter and paginates through every Doc/Sheet you can see (up to
--max-files, default 2000 in this mode) — a full-Drive scan for when a day-bounded pass
finds nothing. It costs one extra API call per file, so it's slower; never trigger it
without telling the user first.

`search-content` full-text searches Doc/Sheet content (Drive's own search index — already
covers everything you can see, no day/--all tiering needed) and returns an excerpt per
match. Needs the spreadsheets.readonly scope in addition to drive.readonly, to read every
tab of a matching spreadsheet rather than just the first one.

Either action can print {"needs_auth": true, "run": "..."} if the token lacks a
required scope.
"""

from __future__ import annotations

import argparse

from _common import run


def main() -> None:
    p = argparse.ArgumentParser(description="Google Drive comments and content search.")
    sub = p.add_subparsers(dest="action", required=True)

    mc = sub.add_parser(
        "mentioned-comments",
        help="Unresolved comments in Docs/Sheets where you are @mentioned or assigned",
    )
    mc.add_argument("--days", type=int, default=30, help="Look back this many days (default 30); ignored if --all is set")
    mc.add_argument("--max-files", type=int, default=None, help="Max files to check (default 50, or 2000 with --all)")
    mc.add_argument("--all", action="store_true", help="Full scan: ignore --days, paginate through every Doc/Sheet you can access")

    sc = sub.add_parser(
        "search-content",
        help="Full-text search Doc/Sheet content, with an excerpt per match",
    )
    sc.add_argument("--query", required=True, help="Text to search for")
    sc.add_argument("--max-files", type=int, default=20, help="Max matching files to return (default 20)")
    sc.add_argument("--context-chars", type=int, default=200, help="Characters of context around the match in each excerpt (default 200)")

    args = p.parse_args()

    from sophonic import gdrive

    if args.action == "mentioned-comments":
        days = None if args.all else args.days
        max_files = args.max_files if args.max_files is not None else (2000 if args.all else 50)
        run(gdrive.list_mentioned_comments, days=days, max_files=max_files)
    else:
        run(
            gdrive.search_content,
            args.query,
            max_files=args.max_files,
            context_chars=args.context_chars,
        )


if __name__ == "__main__":
    main()
