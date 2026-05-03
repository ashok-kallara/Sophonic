"""Tool registry: maps tool names to callables, gated by feature flags."""

from __future__ import annotations

from typing import Any, Callable

from akashic.config import load_config

_REGISTRY: dict[str, Callable[..., Any]] = {}


def register(name: str, fn: Callable[..., Any]) -> None:
    _REGISTRY[name] = fn


def get_registry() -> dict[str, Callable[..., Any]]:
    return dict(_REGISTRY)


def build_registry() -> dict[str, Callable[..., Any]]:
    """Rebuild registry from scratch based on enabled features."""
    _REGISTRY.clear()

    from akashic.tools import obsidian, reminders

    for name, fn in obsidian.TOOLS.items():
        register(name, fn)
    for name, fn in reminders.TOOLS.items():
        register(name, fn)

    cfg = load_config().features

    if cfg.google:
        try:
            from akashic.tools import gcal, gmail
            for name, fn in gcal.TOOLS.items():
                register(name, fn)
            for name, fn in gmail.TOOLS.items():
                register(name, fn)
        except ImportError:
            pass

    if cfg.slack:
        try:
            from akashic.tools import slack_web
            for name, fn in slack_web.TOOLS.items():
                register(name, fn)
        except ImportError:
            pass

    if cfg.zoom:
        try:
            from akashic.tools import zoom
            for name, fn in zoom.TOOLS.items():
                register(name, fn)
        except ImportError:
            pass

    return get_registry()
