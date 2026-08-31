"""Smoke tests: every fetch script runs and emits a single valid JSON object.

These invoke the scripts as real subprocesses (the same way skills call them over Bash)
and assert the output parses as JSON. They run without credentials, so auth-bound
scripts return a `needs_auth`/empty/`error` stub rather than real data — that's fine; the
contract we verify is "prints parseable JSON and exits".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _run(*argv: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / argv[0]), *argv[1:]],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    # stdout must be exactly one JSON object; stderr may carry warnings.
    return proc.stdout


@pytest.mark.parametrize("argv", [
    ("doctor.py",),
    ("zoom.py", "check-auth"),
    ("gtasks.py", "list"),
    ("gdrive.py", "mentioned-comments"),
    ("config.py", "show"),
    ("config.py", "get", "vault.path"),
    ("raindrop.py", "check-auth"),
    ("raindrop.py", "collections"),
])
def test_script_emits_valid_json(argv, monkeypatch):
    monkeypatch.delenv("ZOOM_COOKIES", raising=False)
    monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    out = _run(*argv)
    parsed = json.loads(out)  # raises if not valid JSON
    assert isinstance(parsed, (dict, list))
