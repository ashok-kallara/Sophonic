#!/usr/bin/env python3
"""Read/write Sophonic config (~/.sophonic/config.toml + .env) → JSON.

    uv run python scripts/config.py show
    uv run python scripts/config.py get vault.path
    uv run python scripts/config.py set vault.path /Users/me/vault
    uv run python scripts/config.py set-secret ZOOM_COOKIES --stdin   # paste, then Enter

Thin shim over sophonic.configcli (also exposed as the `sophonic-config` console script).
Secrets go to ~/.sophonic/.env (0600); prefer --stdin.
"""

import _common  # noqa: F401  (bootstraps sys.path so `sophonic` imports uninstalled)
from sophonic.configcli import main

if __name__ == "__main__":
    raise SystemExit(main())
