"""Tests for the config_io persistence core (config.toml + .env)."""

from __future__ import annotations

import os
import stat

import pytest

from sophonic import config_io


def test_set_key_round_trip(tmp_config):
    config_io.set_key("llm.model", "gpt-4o")
    assert config_io.read_raw()["llm"]["model"] == "gpt-4o"
    # effective config reflects it (write_raw cleared the cache)
    from sophonic.config import load_config
    assert load_config().llm.model == "gpt-4o"


def test_set_key_coerces_bool(tmp_config):
    coerced = config_io.set_key("features.gitlab", "true")
    assert coerced is True
    assert config_io.read_raw()["features"]["gitlab"] is True


def test_set_key_coerces_int(tmp_config):
    coerced = config_io.set_key("llm.max_tokens", "8192")
    assert coerced == 8192
    assert isinstance(config_io.read_raw()["llm"]["max_tokens"], int)


def test_set_key_rejects_invalid_bool(tmp_config):
    with pytest.raises(ValueError):
        config_io.set_key("features.gitlab", "notabool")


def test_set_key_rejects_invalid_provider(tmp_config):
    # coercion passes (it's a string) but Config validation rejects it
    with pytest.raises(Exception):
        config_io.set_key("llm.provider", "banana")


def test_set_key_unknown_key(tmp_config):
    with pytest.raises(KeyError):
        config_io.set_key("bogus.key", "x")


def test_unset_key_removes_and_prunes(tmp_config):
    config_io.set_key("llm.model", "gpt-4o")
    assert config_io.unset_key("llm.model") is True
    raw = config_io.read_raw()
    assert "llm" not in raw  # empty table pruned
    assert config_io.unset_key("llm.model") is False  # already gone


def test_set_secret_writes_env_0600(tmp_config):
    config_io.set_secret("ANTHROPIC_API_KEY", "sk-test")
    env = config_io.env_file()
    assert "ANTHROPIC_API_KEY=sk-test" in env.read_text()
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
    """`max_tokens` (contains 'token') and the client-secret *path* are not secrets
    and must stay visible."""
    data = config_io.redacted()
    assert data["llm"]["max_tokens"] == 4096
    assert data["google"]["client_secret_file"] != "***"
