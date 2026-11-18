"""Tests for `sophonic-doctor`: the Zoom cookie check is an optional fallback.

The default Zoom path is the Zoom MCP (called by Claude, invisible to this script), so a
missing/expired cookie session must be reported but must not fail the overall result.
"""

from __future__ import annotations

import pytest

from sophonic import doctorcli
from sophonic.config import Config, FeaturesConfig


@pytest.fixture
def zoom_only(monkeypatch, use_fixture_vault):
    """Config with only the vault + Zoom checks active (no Google/Slack/GitLab I/O)."""
    cfg = Config(
        features=FeaturesConfig(
            google=False, slack=False, zoom=True, gitlab=False, raindrop=False
        )
    )
    cfg.vault.path = use_fixture_vault
    monkeypatch.setattr("sophonic.config.load_config", lambda: cfg)
    return cfg


def _zoom_check(result: dict) -> dict:
    return next(c for c in result["checks"] if c["name"] == "zoom")


def test_zoom_cookie_failure_is_optional_and_does_not_fail_overall(monkeypatch, zoom_only):
    monkeypatch.setattr(
        "sophonic.zoom.check_auth", lambda: {"ok": False, "detail": "ZOOM_COOKIES not set"}
    )
    result = doctorcli.doctor()

    zoom = _zoom_check(result)
    assert zoom["ok"] is False
    assert zoom["optional"] is True
    assert "ZOOM_COOKIES not set" in zoom["detail"]
    assert "MCP" in zoom["detail"]  # tells the reader the cookie path is only a fallback
    assert result["ok"] is True  # vault is fine; the optional fallback doesn't count


def test_zoom_cookie_success_is_reported_ok(monkeypatch, zoom_only):
    monkeypatch.setattr(
        "sophonic.zoom.check_auth", lambda: {"ok": True, "detail": "Zoom web session valid"}
    )
    result = doctorcli.doctor()

    assert _zoom_check(result)["ok"] is True
    assert result["ok"] is True


def test_required_check_failure_still_fails_overall(monkeypatch, zoom_only):
    zoom_only.vault.path = zoom_only.vault.path / "does-not-exist"
    monkeypatch.setattr(
        "sophonic.zoom.check_auth", lambda: {"ok": True, "detail": "Zoom web session valid"}
    )
    assert doctorcli.doctor()["ok"] is False
