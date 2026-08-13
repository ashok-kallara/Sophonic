#!/usr/bin/env python3
"""Authenticate the auth-bound integrations. Run these in YOUR terminal — they open a
browser (Google) or read a local Keychain/session (Slack), which Claude Code cannot do.

    uv run python scripts/auth.py google   # opens a browser for OAuth consent
    uv run python scripts/auth.py slack    # reads the Slack desktop app session
    uv run python scripts/auth.py zoom     # prints how to paste your Zoom cookies

Prints human-readable status (not JSON) — this is an interactive terminal utility.
"""

from __future__ import annotations

import argparse
import os

from _common import emit  # noqa: F401  (kept for the sys.path bootstrap)


def _google() -> int:
    from sophonic.google_auth import get_credentials

    get_credentials()  # runs the desktop OAuth flow if needed
    print("✓ Google authentication successful.")
    return 0


def _slack() -> int:
    from sophonic import slack_local

    try:
        token, d_cookie = slack_local._get_credentials()
    except slack_local.SlackAuthError as exc:
        print(f"✗ Slack auth failed: {exc}")
        print("  Make sure the Slack desktop app is installed and signed in,")
        print("  then approve the one-time Keychain prompt for 'Slack Safe Storage'.")
        return 1
    identity = slack_local._api("auth.test", {}, token, d_cookie)
    print(f"✓ Slack OK — signed in as {identity.get('user', '?')} in {identity.get('team', '?')}.")
    return 0


def _zoom() -> int:
    if os.environ.get("ZOOM_COOKIES"):
        print("✓ Zoom cookies are set. Try: uv run python scripts/zoom.py notes")
        return 0
    print(
        "Zoom needs your web-session cookies (browser automation is blocked in managed browsers).\n"
        "  1. Log in to https://zoom.us, open DevTools → Network.\n"
        "  2. Click any request to zoom.us → Request Headers → copy the whole 'Cookie:' value.\n"
        "  3. Run:  uv run python scripts/config.py set-secret ZOOM_COOKIES --stdin\n"
        "     then paste on one line and press Return.  (Tip: pbpaste | ... --stdin)"
    )
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Authenticate Sophonic integrations.")
    p.add_argument("service", choices=["google", "slack", "zoom"])
    args = p.parse_args()
    raise SystemExit({"google": _google, "slack": _slack, "zoom": _zoom}[args.service]())


if __name__ == "__main__":
    main()
