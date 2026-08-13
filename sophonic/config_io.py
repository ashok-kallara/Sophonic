"""Read/write helpers for ~/.sophonic/config.toml and ~/.sophonic/.env.

Shared by the interactive wizard (`sophonic init`) and the non-interactive
`sophonic config …` commands, so both persist configuration identically.
"""

from __future__ import annotations

import tomllib
import types
import typing
from pathlib import Path
from typing import Any, Union, get_args, get_origin

import tomli_w

from sophonic.config import Config, config_dir, load_config

# Config keys whose *values* are secrets (masked when displaying config).
# Kept precise so non-secret keys like `client_secret_file` (a path) and
# `max_tokens` (an int, contains "token") are NOT masked.
_SECRET_KEYS = {"token", "password", "api_key", "secret_key", "access_token", "client_secret"}


def config_file() -> Path:
    return config_dir() / "config.toml"


def env_file() -> Path:
    return config_dir() / ".env"


# ── config.toml ────────────────────────────────────────────────────────────────

def read_raw() -> dict[str, Any]:
    """Return the persisted config.toml as a dict ({} if it does not exist)."""
    path = config_file()
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def write_raw(raw: dict[str, Any]) -> None:
    """Serialize the config dict to config.toml (0600) and invalidate the cache."""
    config_dir()  # ensure ~/.sophonic exists with tight perms
    path = config_file()
    with open(path, "wb") as f:
        tomli_w.dump(raw, f)
    path.chmod(0o600)
    load_config.cache_clear()


def _expected_type(dotted: str) -> Any:
    """Resolve the annotated type of a dotted key against the Config models."""
    model: Any = Config
    parts = dotted.split(".")
    for i, part in enumerate(parts):
        fields = getattr(model, "model_fields", None)
        if not fields or part not in fields:
            raise KeyError(f"Unknown config key: {dotted!r}")
        annotation = fields[part].annotation
        if i == len(parts) - 1:
            return annotation
        model = annotation  # descend into the nested model
    return None


def _coerce(dotted: str, value: str) -> Any:
    """Coerce a string value to the type expected by the config field."""
    annotation = _expected_type(dotted)
    # Unwrap Optional[X] / X | None
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        annotation = non_none[0] if len(non_none) == 1 else annotation

    if annotation is bool:
        low = value.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"{dotted} expects a boolean (true/false), got {value!r}")
    if annotation is int:
        return int(value)
    if get_origin(annotation) is list:
        return [v.strip() for v in value.split(",") if v.strip()]
    return value


def set_key(dotted: str, value: str) -> Any:
    """Set a dotted config key (e.g. 'llm.model'), validate, and persist. Returns the coerced value."""
    coerced = _coerce(dotted, value)
    raw = read_raw()
    parts = dotted.split(".")
    node = raw
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise ValueError(f"Cannot set {dotted!r}: {part!r} is not a table")
    node[parts[-1]] = coerced

    Config.model_validate(raw)  # reject invalid combinations before writing
    write_raw(raw)
    return coerced


def unset_key(dotted: str) -> bool:
    """Remove a dotted config key. Returns True if something was removed."""
    raw = read_raw()
    parts = dotted.split(".")
    nodes = [raw]
    for part in parts[:-1]:
        cur = nodes[-1].get(part)
        if not isinstance(cur, dict):
            return False
        nodes.append(cur)
    if parts[-1] not in nodes[-1]:
        return False
    del nodes[-1][parts[-1]]
    # prune now-empty parent tables
    for part, parent in zip(reversed(parts[:-1]), reversed(nodes[:-1])):
        if parent.get(part) == {}:
            del parent[part]
    Config.model_validate(raw)
    write_raw(raw)
    return True


# ── .env secrets ────────────────────────────────────────────────────────────────

def _read_env_lines() -> list[str]:
    path = env_file()
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _write_env_lines(lines: list[str]) -> None:
    config_dir()
    path = env_file()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    load_config.cache_clear()


def set_secret(name: str, value: str) -> None:
    """Upsert a KEY=VALUE line in ~/.sophonic/.env (0600), preserving other lines."""
    lines = _read_env_lines()
    prefix = f"{name}="
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix) and not line.lstrip().startswith("#"):
            lines[i] = f"{name}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{name}={value}")
    _write_env_lines(lines)


def unset_secret(name: str) -> bool:
    """Remove a secret line from .env. Returns True if removed."""
    lines = _read_env_lines()
    prefix = f"{name}="
    kept = [ln for ln in lines if not (ln.strip().startswith(prefix) and not ln.lstrip().startswith("#"))]
    if len(kept) == len(lines):
        return False
    _write_env_lines(kept)
    return True


def env_secret_names() -> list[str]:
    """Names of secrets currently stored in .env (values never returned)."""
    names = []
    for line in _read_env_lines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            names.append(stripped.split("=", 1)[0])
    return names


# ── display ───────────────────────────────────────────────────────────────────

def _is_secret_key(key: str) -> bool:
    low = key.lower()
    return low in _SECRET_KEYS or low.endswith("_token") or low.endswith("_password")


def _mask(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if _is_secret_key(k) and v else _mask(v)) for k, v in value.items()}
    return value


def redacted() -> dict[str, Any]:
    """Effective config as a JSON-able dict with secret-looking values masked."""
    data = load_config().model_dump(mode="json")
    return _mask(data)
