"""Shared bootstrap + JSON output for Sophonic plugin scripts.

The scripts are thin argv → JSON shims. They exist only because a Claude subagent
cannot natively perform OAuth / keychain / cookie-authenticated network calls; skills
invoke them over Bash and read the JSON they print. Anything Claude can do with its own
tools (editing the Obsidian vault) is a pure skill, not a script.
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Callable

# Make the `sophonic` package importable whether or not the project is installed.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def emit(obj: Any) -> None:
    """Print a single JSON object to stdout (the script's entire contract)."""
    print(json.dumps(obj, indent=2, default=str))


def run(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Call fn and emit its result as JSON; on failure emit {"error": ...} and exit 1."""
    try:
        emit(fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 — normalize into a caller-friendly JSON error
        emit({"error": str(exc)})
        raise SystemExit(1)
