"""Tests for config models and environment variable handling."""

from __future__ import annotations

from unittest.mock import patch

import pytest

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
    cfg = load_config()
    assert cfg.gitlab.token == "glpat-test-token"
    load_config.cache_clear()


def test_build_registry_respects_obsidian_flag(monkeypatch):
    """When features.obsidian = False, obsidian_* tools are absent from registry."""
    monkeypatch.setenv("SOPHONIC_VAULT", "/tmp/sophonic_test")
    from sophonic.config import load_config
    load_config.cache_clear()

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
    load_config.cache_clear()
