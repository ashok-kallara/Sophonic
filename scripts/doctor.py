#!/usr/bin/env python3
"""Report per-integration config/auth status as JSON, with fix commands for gaps.

    uv run python scripts/doctor.py

The `setup` skill drives this: it reads the checks, interviews the user for whatever is
missing, and applies fixes. There is no LLM check — Claude Code provides the model.
"""

from __future__ import annotations

import os
from pathlib import Path

from _common import emit


def doctor() -> dict:
    from sophonic.config import config_dir, load_config

    cfg = load_config()
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, fix: str = "") -> None:
        entry = {"name": name, "ok": ok, "detail": detail}
        if not ok and fix:
            entry["fix"] = fix
        checks.append(entry)

    # vault — used by the pure-skill vault edits (Claude reads/writes it directly)
    vault = Path(cfg.vault.path)
    add("vault", vault.is_dir(), f"vault.path = {vault}",
        "uv run python scripts/config.py set vault.path <path>  (and create the directory)")

    # google
    if cfg.features.google:
        secret = Path(str(cfg.google.client_secret_file).replace("~", str(Path.home())))
        add("google.client_secret", secret.exists(), f"{secret}",
            "Download an OAuth desktop client JSON and save it there")
        token = config_dir() / "tokens" / "google.json"
        add("google.auth", token.exists(), f"token: {token}",
            "uv run python scripts/auth.py google")

    # slack — reads the desktop app session (no browser)
    if cfg.features.slack:
        from sophonic import slack_local
        try:
            token, d_cookie = slack_local._get_credentials()
            ok = bool(slack_local._api("auth.test", {}, token, d_cookie).get("ok"))
            detail = "Slack desktop session readable + auth.test ok" if ok else "auth.test failed"
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, str(exc)
        add("slack", ok, detail, "uv run python scripts/auth.py slack  (approve the Keychain prompt)")

    # zoom — pasted web-session cookies; probe validity, not just presence
    if cfg.features.zoom:
        from sophonic.zoom import check_auth
        probe = check_auth()
        add("zoom", probe["ok"], probe["detail"],
            "uv run python scripts/config.py set-secret ZOOM_COOKIES --stdin  (paste the zoom.us 'Cookie:' header)")

    # gitlab
    if cfg.features.gitlab:
        token_present = bool(cfg.gitlab.token or os.environ.get("GITLAB_TOKEN"))
        ok = bool(cfg.gitlab.url) and token_present
        add("gitlab", ok, f"url={cfg.gitlab.url or '(unset)'} token={'set' if token_present else 'missing'}",
            "uv run python scripts/config.py set gitlab.url <url> ; "
            "uv run python scripts/config.py set-secret GITLAB_TOKEN --stdin")

    return {"ok": all(c["ok"] for c in checks), "checks": checks}


if __name__ == "__main__":
    emit(doctor())
