"""Tool registry: maps tool names to callables, gated by feature flags."""

from __future__ import annotations

from typing import Any, Callable

from sophonic.config import load_config

_REGISTRY: dict[str, Callable[..., Any]] = {}


def register(name: str, fn: Callable[..., Any]) -> None:
    _REGISTRY[name] = fn


def get_registry() -> dict[str, Callable[..., Any]]:
    return dict(_REGISTRY)


def build_registry() -> dict[str, Callable[..., Any]]:
    """Rebuild registry from scratch based on enabled features."""
    _REGISTRY.clear()

    cfg = load_config()
    feat = cfg.features

    if feat.obsidian:
        from sophonic.tools import obsidian
        for name, fn in obsidian.TOOLS.items():
            register(name, fn)

    if feat.reminders:
        from sophonic.tools import reminders
        for name, fn in reminders.TOOLS.items():
            register(name, fn)

    if feat.google:
        try:
            from sophonic.tools import gcal, gmail
            for name, fn in {**gcal.TOOLS, **gmail.TOOLS}.items():
                register(name, fn)
        except ImportError:
            pass

    if feat.slack:
        try:
            from sophonic.tools import slack_web
            for name, fn in slack_web.TOOLS.items():
                register(name, fn)
        except ImportError:
            pass

    if feat.zoom:
        try:
            from sophonic.tools import zoom
            for name, fn in zoom.TOOLS.items():
                register(name, fn)
        except ImportError:
            pass

    if feat.gitlab:
        from sophonic.tools.gitlab import build_tools as _build_gitlab
        for name, fn in _build_gitlab(cfg.gitlab).items():
            register(name, fn)

    registry = get_registry()
    from sophonic import skills
    skills.validate(registry)
    return registry
