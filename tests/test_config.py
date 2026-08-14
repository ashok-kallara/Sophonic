"""Tests for config models and environment variable handling."""

from __future__ import annotations

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


def test_config_has_no_llm_field():
    """Claude Code is the model now — there is no LLM config."""
    assert not hasattr(Config(), "llm")


def test_gitlab_token_env_var(monkeypatch):
    from sophonic.config import load_config

    monkeypatch.setenv("GITLAB_TOKEN", "glpat-test-token")
    load_config.cache_clear()
    try:
        assert load_config().gitlab.token == "glpat-test-token"
    finally:
        load_config.cache_clear()


def test_env_file_is_loaded(tmp_config, monkeypatch):
    """A secret present only in ~/.sophonic/.env is loaded by load_config()."""
    from sophonic.config import load_config

    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    tmp_config.mkdir(parents=True, exist_ok=True)
    (tmp_config / ".env").write_text("GITLAB_TOKEN=from-envfile\n")
    load_config.cache_clear()
    try:
        assert load_config().gitlab.token == "from-envfile"
    finally:
        monkeypatch.delenv("GITLAB_TOKEN", raising=False)
        load_config.cache_clear()


def test_real_env_overrides_env_file(tmp_config, monkeypatch):
    """override=False: a real environment variable beats the .env file."""
    from sophonic.config import load_config

    tmp_config.mkdir(parents=True, exist_ok=True)
    (tmp_config / ".env").write_text("GITLAB_TOKEN=from-envfile\n")
    monkeypatch.setenv("GITLAB_TOKEN", "from-real-env")
    load_config.cache_clear()
    try:
        assert load_config().gitlab.token == "from-real-env"
    finally:
        load_config.cache_clear()
