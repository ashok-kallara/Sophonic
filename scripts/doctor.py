#!/usr/bin/env python3
"""Per-integration config/auth status as JSON, with fix commands for gaps.

    uv run python scripts/doctor.py

Thin shim over sophonic.doctorcli (also exposed as the `sophonic-doctor` console script).
The `setup` skill drives this. There is no LLM check — Claude Code provides the model.
"""

import _common  # noqa: F401  (bootstraps sys.path so `sophonic` imports uninstalled)
from sophonic.doctorcli import main

if __name__ == "__main__":
    raise SystemExit(main())
