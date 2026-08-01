"""Tests for config models and environment variable handling."""

from __future__ import annotations

import os
from unittest.mock import patch

from sophonic.config import Config, FeaturesConfig, GitLabConfig


def test_features_obsidian_default_true():
    assert FeaturesConfig().obsidian is True


def test_features_reminders_default_true():
    assert FeaturesConfig().reminders is True


def test_features_gitlab_default_false():
    assert FeaturesConfig().gitlab is False


def test_gitlab_config_defaults():
    cfg = GitLabConfig()
    assert cfg.url == ""
    assert cfg.token == ""
    assert cfg.default_project == ""


def test_config_has_gitlab_field():
    cfg = Config()
    assert isinstance(cfg.gitlab, GitLabConfig)


def test_gitlab_token_env_var(monkeypatch):
    from sophonic.config import load_config
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-test-token")
    load_config.cache_clear()
    try:
        cfg = load_config()
        assert cfg.gitlab.token == "glpat-test-token"
    finally:
        load_config.cache_clear()


def test_build_registry_respects_obsidian_flag(monkeypatch):
    """When features.obsidian = False, obsidian_* tools are absent from registry."""
    monkeypatch.setenv("SOPHONIC_VAULT", "/tmp/sophonic_test")
    from sophonic.config import load_config
    load_config.cache_clear()
    try:
        disabled_cfg = Config(
            features=FeaturesConfig(
                obsidian=False, reminders=False,
                google=False, slack=False, zoom=False, gitlab=False,
            )
        )
        with patch("sophonic.tools.load_config", return_value=disabled_cfg), \
             patch("sophonic.skills.validate"):
            from sophonic.tools import _REGISTRY, build_registry
            _REGISTRY.clear()
            registry = build_registry()

        assert "obsidian_add_task" not in registry
        assert "reminder_create" not in registry
    finally:
        load_config.cache_clear()


def test_env_file_is_loaded(tmp_config, monkeypatch):
    """A key present only in ~/.sophonic/.env is loaded by load_config()."""
    from sophonic.config import load_config

    monkeypatch.delenv("SOPHONIC_LLM_MODEL", raising=False)
    tmp_config.mkdir(parents=True, exist_ok=True)
    (tmp_config / ".env").write_text("SOPHONIC_LLM_MODEL=from-envfile\n")
    load_config.cache_clear()
    try:
        assert load_config().llm.model == "from-envfile"
    finally:
        os.environ.pop("SOPHONIC_LLM_MODEL", None)
        load_config.cache_clear()


def test_real_env_overrides_env_file(tmp_config, monkeypatch):
    """override=False: a real environment variable beats the .env file."""
    from sophonic.config import load_config

    tmp_config.mkdir(parents=True, exist_ok=True)
    (tmp_config / ".env").write_text("SOPHONIC_LLM_MODEL=from-envfile\n")
    monkeypatch.setenv("SOPHONIC_LLM_MODEL", "from-real-env")
    load_config.cache_clear()
    try:
        assert load_config().llm.model == "from-real-env"
    finally:
        load_config.cache_clear()


def test_resolve_llm_api_key_prefers_canonical(monkeypatch):
    from sophonic.config import resolve_llm_api_key

    monkeypatch.setenv("SOPHONIC_LLM_API_KEY", "canonical")
    monkeypatch.setenv("OPENAI_API_KEY", "native")
    assert resolve_llm_api_key("openai") == "canonical"


def test_resolve_llm_api_key_native_fallback(monkeypatch):
    from sophonic.config import resolve_llm_api_key

    monkeypatch.delenv("SOPHONIC_LLM_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-native")
    assert resolve_llm_api_key("anthropic") == "ak-native"


def test_resolve_llm_api_key_litellm_has_no_native(monkeypatch):
    """litellm has no standard env var — only SOPHONIC_LLM_API_KEY applies."""
    from sophonic.config import resolve_llm_api_key

    monkeypatch.delenv("SOPHONIC_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "not-used-for-litellm")
    assert resolve_llm_api_key("litellm") is None


def test_init_writes_config(tmp_config, monkeypatch):
    """`sophonic init` persists prompt answers via config_io (smoke test)."""
    from sophonic import wizard, config_io

    def fake_prompt(label, default="", choices=None, password=False, **kw):
        if "Daily notes directory" in label:
            return "Journal"
        return default if default is not None else ""

    def fake_confirm(label, default=False, **kw):
        return False  # decline all features + all "run auth now?" prompts

    monkeypatch.setattr(wizard.Prompt, "ask", fake_prompt)
    monkeypatch.setattr(wizard.Confirm, "ask", fake_confirm)

    wizard.run_init()

    raw = config_io.read_raw()
    assert raw["vault"]["daily_dir"] == "Journal"
