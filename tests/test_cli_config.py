"""Tests for the `sophonic config …` and `sophonic doctor` CLI commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from sophonic import config_io
from sophonic.cli import app

runner = CliRunner()


def test_config_set_then_get(tmp_config):
    r = runner.invoke(app, ["config", "set", "llm.model", "gpt-4o"])
    assert r.exit_code == 0
    assert json.loads(r.stdout)["value"] == "gpt-4o"

    r = runner.invoke(app, ["config", "get", "llm.model"])
    assert r.exit_code == 0
    assert json.loads(r.stdout) == "gpt-4o"


def test_config_get_unknown_key_exit_1(tmp_config):
    r = runner.invoke(app, ["config", "get", "nope.nope"])
    assert r.exit_code == 1
    assert "error" in json.loads(r.stdout)


def test_config_set_invalid_exit_1(tmp_config):
    r = runner.invoke(app, ["config", "set", "features.gitlab", "notabool"])
    assert r.exit_code == 1
    assert "error" in json.loads(r.stdout)


def test_config_show_redacts_secrets(tmp_config):
    config_io.set_key("gitlab.token", "glpat-secret")
    r = runner.invoke(app, ["config", "show", "--json"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["gitlab"]["token"] == "***"
    assert "_secrets_in_env" in data


def test_config_set_secret_stdin_writes_env(tmp_config):
    r = runner.invoke(app, ["config", "set-secret", "ANTHROPIC_API_KEY", "--stdin"], input="sk-xyz\n")
    assert r.exit_code == 0
    assert "ANTHROPIC_API_KEY=sk-xyz" in config_io.env_file().read_text()


def test_config_set_secret_requires_source(tmp_config):
    r = runner.invoke(app, ["config", "set-secret", "SOME_KEY"])
    assert r.exit_code == 1
    assert "error" in json.loads(r.stdout)


def _disable_browser_features():
    """Skip the slack/zoom doctor checks so tests stay hermetic (no Keychain/network)."""
    config_io.set_key("features.slack", "false")
    config_io.set_key("features.zoom", "false")


def test_doctor_returns_status_json(tmp_config):
    _disable_browser_features()
    r = runner.invoke(app, ["doctor"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert "ok" in data and "checks" in data
    names = {c["name"] for c in data["checks"]}
    assert "vault" in names and "llm" in names


def test_doctor_flags_missing_litellm_api_base(tmp_config):
    _disable_browser_features()
    config_io.set_key("llm.provider", "litellm")  # accepted; api_base still unset
    r = runner.invoke(app, ["doctor"])
    assert r.exit_code == 0
    checks = {c["name"]: c for c in json.loads(r.stdout)["checks"]}
    assert "llm.api_base" in checks
    assert checks["llm.api_base"]["ok"] is False


def test_config_path(tmp_config):
    r = runner.invoke(app, ["config", "path"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["config"].endswith("config.toml")
    assert data["env"].endswith(".env")
