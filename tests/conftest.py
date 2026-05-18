"""Shared pytest fixtures."""

import os
from pathlib import Path

import pytest


FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture(autouse=True)
def use_fixture_vault(tmp_path, monkeypatch):
    """Redirect vault path to a fresh temp copy for each test."""
    import shutil

    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    (vault / "Daily").mkdir(exist_ok=True)

    monkeypatch.setenv("SOPHONIC_VAULT", str(vault))
    # Bust the lru_cache so the new env var is picked up
    from sophonic.config import load_config
    load_config.cache_clear()
    yield vault
    load_config.cache_clear()
