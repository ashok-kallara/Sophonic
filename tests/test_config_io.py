"""Tests for the config_io persistence core (config.toml + .env)."""

from __future__ import annotations

import os
import stat

import pytest

from sophonic import config_io


def test_set_key_round_trip(tmp_config):
    config_io.set_key("vault.daily_dir", "Journal")
    assert config_io.read_raw()["vault"]["daily_dir"] == "Journal"
    # effective config reflects it (write_raw cleared the cache)
    from sophonic.config import load_config
    assert load_config().vault.daily_dir == "Journal"


def test_set_key_coerces_bool(tmp_config):
    coerced = config_io.set_key("features.gitlab", "true")
    assert coerced is True
    assert config_io.read_raw()["features"]["gitlab"] is True


def test_set_key_coerces_list(tmp_config):
    coerced = config_io.set_key("google.scopes", "https://a/x,https://a/y")
    assert coerced == ["https://a/x", "https://a/y"]
    assert config_io.read_raw()["google"]["scopes"] == ["https://a/x", "https://a/y"]


def test_set_key_rejects_invalid_bool(tmp_config):
    with pytest.raises(ValueError):
        config_io.set_key("features.gitlab", "notabool")


def test_set_key_rejects_invalid_value(tmp_config):
    # coercion passes (it's a string) but Config validation rejects the engine choice
    with pytest.raises(Exception):
        config_io.set_key("browser.zoom.engine", "banana")


def test_set_key_unknown_key(tmp_config):
    with pytest.raises(KeyError):
        config_io.set_key("bogus.key", "x")


def test_unset_key_removes_and_prunes(tmp_config):
    config_io.set_key("vault.daily_dir", "Journal")
    assert config_io.unset_key("vault.daily_dir") is True
    raw = config_io.read_raw()
    assert "vault" not in raw  # empty table pruned
    assert config_io.unset_key("vault.daily_dir") is False  # already gone


def test_set_secret_writes_env_0600(tmp_config):
    config_io.set_secret("ZOOM_COOKIES", "cookie-blob")
    env = config_io.env_file()
    assert "ZOOM_COOKIES=cookie-blob" in env.read_text()
    mode = stat.S_IMODE(os.stat(env).st_mode)
    assert mode == 0o600


def test_set_secret_upserts_and_preserves_others(tmp_config):
    config_io.set_secret("KEY_A", "one")
    config_io.set_secret("KEY_B", "two")
    config_io.set_secret("KEY_A", "updated")
    text = config_io.env_file().read_text()
    assert "KEY_A=updated" in text
    assert "KEY_B=two" in text
    assert "KEY_A=one" not in text
    assert set(config_io.env_secret_names()) == {"KEY_A", "KEY_B"}


def test_unset_secret(tmp_config):
    config_io.set_secret("KEY_A", "one")
    assert config_io.unset_secret("KEY_A") is True
    assert config_io.env_secret_names() == []
    assert config_io.unset_secret("KEY_A") is False


def test_redacted_masks_secret_keys(tmp_config):
    config_io.set_key("gitlab.url", "https://gitlab.example.com")
    config_io.set_key("gitlab.token", "glpat-supersecret")
    data = config_io.redacted()
    assert data["gitlab"]["url"] == "https://gitlab.example.com"
    assert data["gitlab"]["token"] == "***"  # masked


def test_redacted_does_not_mask_non_secret_lookalikes(tmp_config):
    """The client-secret *path* is not a secret and must stay visible."""
    data = config_io.redacted()
    assert data["google"]["client_secret_file"] != "***"
    assert data["gitlab"]["default_project"] == ""
