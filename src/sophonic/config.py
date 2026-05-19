"""Configuration: loads ~/.sophonic/config.toml + environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

_CONFIG_DIR = Path.home() / ".sophonic"
_CONFIG_FILE = _CONFIG_DIR / "config.toml"


class VaultConfig(BaseModel):
    path: Path = Path.home() / "Documents/Obsidian/ak-work"
    daily_dir: str = "Daily"
    daily_prefix: str = "DAILY-"
    meetings_dir: str = "Work/Meetings"


class FeaturesConfig(BaseModel):
    obsidian: bool = True
    reminders: bool = True
    google: bool = True
    slack: bool = True
    zoom: bool = True
    gitlab: bool = False


class GoogleConfig(BaseModel):
    client_secret_file: Path = _CONFIG_DIR / "google_client_secret.json"
    scopes: list[str] = Field(
        default=["https://www.googleapis.com/auth/calendar.readonly",
                 "https://www.googleapis.com/auth/gmail.readonly"]
    )


class BrowserEngineConfig(BaseModel):
    engine: str = "chromium"  # "chromium" | "chrome" | "island"

    @model_validator(mode="after")
    def validate_engine(self) -> "BrowserEngineConfig":
        if self.engine not in ("chromium", "chrome", "island"):
            raise ValueError(f"Invalid browser engine: {self.engine!r}. Choose chromium, chrome, or island.")
        return self


class BrowserIslandConfig(BaseModel):
    path: str = ""  # auto-detect if empty


class BrowserConfig(BaseModel):
    slack: BrowserEngineConfig = BrowserEngineConfig(engine="chromium")
    zoom: BrowserEngineConfig = BrowserEngineConfig(engine="chromium")
    island: BrowserIslandConfig = BrowserIslandConfig()


class SlackConfig(BaseModel):
    workspace_url: str = "https://app.slack.com"


class ZoomConfig(BaseModel):
    recordings_url: str = "https://zoom.us/recording"
    save_transcripts: bool = True  # auto-file transcripts as meeting notes


class LLMConfig(BaseModel):
    model: str = "claude-sonnet-4-6"


class GitLabConfig(BaseModel):
    url: str = ""
    token: str = ""
    default_project: str = ""


class Config(BaseModel):
    vault: VaultConfig = VaultConfig()
    features: FeaturesConfig = FeaturesConfig()
    google: GoogleConfig = GoogleConfig()
    browser: BrowserConfig = BrowserConfig()
    slack: SlackConfig = SlackConfig()
    zoom: ZoomConfig = ZoomConfig()
    llm: LLMConfig = LLMConfig()
    gitlab: GitLabConfig = GitLabConfig()


@lru_cache(maxsize=1)
def load_config() -> Config:
    raw: dict = {}
    if _CONFIG_FILE.exists():
        import tomllib
        with open(_CONFIG_FILE, "rb") as f:
            raw = tomllib.load(f)

    # Allow env overrides for the most common settings
    if vault_path := os.environ.get("SOPHONIC_VAULT"):
        raw.setdefault("vault", {})["path"] = vault_path

    if gitlab_token := os.environ.get("GITLAB_TOKEN"):
        raw.setdefault("gitlab", {})["token"] = gitlab_token

    return Config.model_validate(raw)


def config_dir() -> Path:
    """Return ~/.sophonic/, creating it with tight permissions on first call."""
    _CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return _CONFIG_DIR
