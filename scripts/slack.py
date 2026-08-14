#!/usr/bin/env python3
"""Slack via the desktop app's local session (read-only) → JSON.

    uv run python scripts/slack.py unread
    uv run python scripts/slack.py digest --per-channel 8 --max-channels 25
    uv run python scripts/slack.py followups --days 2 --max-items 20
    uv run python scripts/slack.py search --query "deploy freeze"

`digest` splits unread into actionable (DMs/@-mentions) vs informational channels.
`followups` finds mentions/DMs/saved-for-later that likely still need a reply.
On auth failure the result carries {"needs_auth": true, "run": "..."}.
"""

from __future__ import annotations

import argparse

from _common import run


def main() -> None:
    p = argparse.ArgumentParser(description="Slack desktop-session reader (read-only).")
    sub = p.add_subparsers(dest="action", required=True)

    sub.add_parser("unread", help="Unread channels, group DMs, and DMs")

    d = sub.add_parser("digest", help="Unread with content, split actionable vs informational")
    d.add_argument("--per-channel", type=int, default=8)
    d.add_argument("--max-channels", type=int, default=25)

    f = sub.add_parser("followups", help="Mentions/DMs/saved-for-later likely needing a reply")
    f.add_argument("--days", type=int, default=2)
    f.add_argument("--max-items", type=int, default=20)

    s = sub.add_parser("search", help="Search messages")
    s.add_argument("--query", required=True)

    args = p.parse_args()

    from sophonic import slack_local

    if args.action == "unread":
        run(slack_local.unread)
    elif args.action == "digest":
        run(slack_local.unread_digest, per_channel=args.per_channel, max_channels=args.max_channels)
    elif args.action == "followups":
        run(slack_local.followups, days=args.days, max_items=args.max_items)
    else:
        run(slack_local.search, args.query)


if __name__ == "__main__":
    main()
