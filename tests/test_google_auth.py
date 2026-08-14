"""Tests for the Google OAuth client-secret guard."""

from __future__ import annotations

import json

import pytest

from sophonic.google_auth import _require_desktop_client


def test_rejects_web_client(tmp_path):
    secret = tmp_path / "client.json"
    secret.write_text(json.dumps({"web": {"client_id": "x", "redirect_uris": ["http://localhost:8080/oauth/callback"]}}))
    with pytest.raises(ValueError, match="Desktop app"):
        _require_desktop_client(secret)


def test_accepts_desktop_client(tmp_path):
    secret = tmp_path / "client.json"
    secret.write_text(json.dumps({"installed": {"client_id": "x"}}))
    _require_desktop_client(secret)  # should not raise


def test_unreadable_secret_raises_value_error(tmp_path):
    secret = tmp_path / "client.json"
    secret.write_text("{ not json")
    with pytest.raises(ValueError, match="Could not read"):
        _require_desktop_client(secret)


# ── scope-coverage detection (forces re-consent when a scope is added) ────────────

_CAL = "https://www.googleapis.com/auth/calendar.readonly"
_GMAIL = "https://www.googleapis.com/auth/gmail.readonly"
_TASKS = "https://www.googleapis.com/auth/tasks.readonly"


def test_token_covers_true_when_all_scopes_granted(tmp_path):
    from sophonic.google_auth import _token_covers

    tok = tmp_path / "google.json"
    tok.write_text(json.dumps({"token": "x", "scopes": [_CAL, _GMAIL, _TASKS]}))
    assert _token_covers(tok, [_CAL, _TASKS]) is True


def test_token_covers_false_when_scope_missing(tmp_path):
    from sophonic.google_auth import _token_covers

    tok = tmp_path / "google.json"
    tok.write_text(json.dumps({"token": "x", "scopes": [_CAL, _GMAIL]}))
    # tasks.readonly newly added to config but not granted → must re-consent
    assert _token_covers(tok, [_CAL, _GMAIL, _TASKS]) is False


def test_token_covers_false_when_file_missing(tmp_path):
    from sophonic.google_auth import _token_covers

    assert _token_covers(tmp_path / "nope.json", [_CAL]) is False
