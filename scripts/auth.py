#!/usr/bin/env python3
"""Authenticate the auth-bound integrations. Run these in YOUR terminal — they open a
browser (Google) or read a local Keychain/session (Slack), which Claude Code cannot do.

    uv run python scripts/auth.py google   # opens a browser for OAuth consent
    uv run python scripts/auth.py slack    # reads the Slack desktop app session
    uv run python scripts/auth.py zoom     # prints how to paste your Zoom cookies

Thin shim over sophonic.authcli (also exposed as the `sophonic-auth` console script).
"""

import _common  # noqa: F401  (bootstraps sys.path so `sophonic` imports uninstalled)
from sophonic.authcli import main

if __name__ == "__main__":
    raise SystemExit(main())
