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
    # Zoom is the only browser-driven integration (Slack reads its desktop-app session).
    zoom: BrowserEngineConfig = BrowserEngineConfig(engine="chromium")
    island: BrowserIslandConfig = BrowserIslandConfig()


class SlackConfig(BaseModel):
    # Workspace host for token derivation, e.g. "acme.enterprise.slack.com". Optional:
    # the token is usually found automatically; set this only if auto-detection fails.
    workspace_host: str = ""


# Providers that speak the OpenAI wire format (a LiteLLM proxy is OpenAI-compatible).
OPENAI_COMPATIBLE_PROVIDERS = ("openai", "litellm")
LLM_PROVIDERS = ("anthropic",) + OPENAI_COMPATIBLE_PROVIDERS

# One provider-agnostic env var for the LLM key — set this and it works for any provider.
LLM_API_KEY_ENV = "SOPHONIC_LLM_API_KEY"
# Provider-native env vars honored as a fallback (litellm has no standard one).
_NATIVE_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def llm_api_key_envs(provider: str) -> list[str]:
    """Env vars consulted, in order, for a provider's LLM API key."""
    envs = [LLM_API_KEY_ENV]
    native = _NATIVE_KEY_ENV.get(provider)
    if native:
        envs.append(native)
    return envs


def resolve_llm_api_key(provider: str) -> str | None:
    """Return the first non-empty LLM API key found for the provider, else None."""
    for name in llm_api_key_envs(provider):
        if value := os.environ.get(name):
            return value
    return None


class LLMConfig(BaseModel):
    provider: str = "anthropic"          # one of LLM_PROVIDERS
    model: str = "claude-sonnet-4-6"
    api_base: str | None = None          # OpenAI-compatible base_url (Ollama/LiteLLM proxy/etc.)
    max_tokens: int = 4096

    @model_validator(mode="after")
    def validate_provider(self) -> "LLMConfig":
        if self.provider not in LLM_PROVIDERS:
            raise ValueError(
                f"Invalid llm provider: {self.provider!r}. Choose one of {', '.join(LLM_PROVIDERS)}."
            )
        return self


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
    llm: LLMConfig = LLMConfig()
    gitlab: GitLabConfig = GitLabConfig()


@lru_cache(maxsize=1)
def load_config() -> Config:
    # Load ~/.sophonic/.env into the environment so persisted secrets take effect.
    # override=False keeps any real environment variable authoritative.
    _env_file = _CONFIG_DIR / ".env"
    if _env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)

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

    if llm_provider := os.environ.get("SOPHONIC_LLM_PROVIDER"):
        raw.setdefault("llm", {})["provider"] = llm_provider

    if llm_model := os.environ.get("SOPHONIC_LLM_MODEL"):
        raw.setdefault("llm", {})["model"] = llm_model

    return Config.model_validate(raw)


def config_dir() -> Path:
    """Return ~/.sophonic/, creating it with tight permissions on first call."""
    _CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return _CONFIG_DIR
