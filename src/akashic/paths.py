"""Vault path helpers derived from config."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from akashic.config import load_config


def vault_root() -> Path:
    return Path(load_config().vault.path)


def daily_note_path(for_date: date | None = None) -> Path:
    cfg = load_config().vault
    d = for_date or date.today()
    filename = f"{cfg.daily_prefix}{d.isoformat()}.md"
    return vault_root() / cfg.daily_dir / filename


def meetings_dir() -> Path:
    return vault_root() / load_config().vault.meetings_dir
