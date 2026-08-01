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
