"""Interactive setup wizard (`sophonic init`) — rich prompts, needs a real TTY.

Persists via the same `config_io` core the non-interactive `sophonic config …`
commands use, so terminal setup and plugin-driven setup can't diverge.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt

from sophonic import config_io
from sophonic.config import (
    LLM_API_KEY_ENV,
    LLM_PROVIDERS,
    OPENAI_COMPATIBLE_PROVIDERS,
    Config,
    load_config,
)

console = Console()


def _dig(data: dict, dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _put(raw: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = raw
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _install_playwright_browser() -> None:
    """Download the Playwright browser (headless Chromium) used by Zoom.

    Runs against the current interpreter's Playwright, so it works whether Sophonic
    was installed as a uv tool or run from a project venv. Idempotent — skips if the
    browser is already present.
    """
    import subprocess
    import sys

    console.print("[dim]Downloading the Playwright browser (Chromium, ~150 MB) — one time…[/dim]")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        console.print("  [green]Browser ready.[/green]")
    except Exception as exc:  # noqa: BLE001 — surface any failure, keep setup going
        console.print(
            f"  [yellow]Browser install failed:[/yellow] {exc}\n"
            "  Run it manually later: [cyan]playwright install chromium[/cyan]"
        )


def run_init() -> None:
    """Walk the user through installing dependencies and configuring every integration."""
    console.print("[bold]Sophonic setup[/bold] — press Enter to keep the current value.\n")

    # ── dependencies (install first, then configure) ─────────────────────────
    console.rule("Dependencies")
    if Confirm.ask("Install the Playwright browser used by Zoom (~150 MB)?", default=True):
        _install_playwright_browser()

    current = load_config().model_dump(mode="json")
    defaults = Config().model_dump(mode="json")
    raw = config_io.read_raw()

    def ask_str(dotted: str, label: str) -> None:
        val = Prompt.ask(label, default=str(_dig(current, dotted)))
        if val != _dig(defaults, dotted):
            _put(raw, dotted, val)

    def ask_bool(dotted: str, label: str) -> bool:
        val = Confirm.ask(label, default=bool(_dig(current, dotted)))
        if val != _dig(defaults, dotted):
            _put(raw, dotted, val)
        return val

    def ask_choice(dotted: str, label: str, choices: list[str]) -> str:
        val = Prompt.ask(label, choices=choices, default=str(_dig(current, dotted)))
        if val != _dig(defaults, dotted):
            _put(raw, dotted, val)
        return val

    def ask_secret(name: str, label: str) -> None:
        val = Prompt.ask(f"{label} [dim](stored in ~/.sophonic/.env; blank to skip)[/dim]",
                         password=True, default="")
        if val:
            config_io.set_secret(name, val)
            console.print(f"  [green]saved[/green] {name} → ~/.sophonic/.env")

    # ── vault ───────────────────────────────────────────────────────────────
    console.rule("Vault")
    ask_str("vault.path", "Obsidian vault path")
    ask_str("vault.daily_dir", "Daily notes directory")
    ask_str("vault.daily_prefix", "Daily note filename prefix")
    ask_str("vault.meetings_dir", "Meeting notes directory")

    # ── features ────────────────────────────────────────────────────────────
    console.rule("Features")
    ask_bool("features.obsidian", "Enable Obsidian")
    ask_bool("features.reminders", "Enable reminders")
    google_on = ask_bool("features.google", "Enable Google (Calendar + Gmail)")
    slack_on = ask_bool("features.slack", "Enable Slack")
    zoom_on = ask_bool("features.zoom", "Enable Zoom")
    gitlab_on = ask_bool("features.gitlab", "Enable GitLab")

    # ── llm ─────────────────────────────────────────────────────────────────
    console.rule("LLM")
    provider = ask_choice("llm.provider", "LLM provider", list(LLM_PROVIDERS))
    ask_str("llm.model", "Model")
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        base_hint = "LiteLLM proxy base URL" if provider == "litellm" else "OpenAI-compatible base URL (blank for api.openai.com)"
        ask_str("llm.api_base", base_hint)
    # One key for any provider — stored as SOPHONIC_LLM_API_KEY.
    ask_secret(LLM_API_KEY_ENV, "LLM API key")

    # ── google ──────────────────────────────────────────────────────────────
    if google_on:
        console.rule("Google")
        ask_str("google.client_secret_file", "OAuth client secret JSON path")
        console.print("  [dim]Download the desktop OAuth client JSON from Google Cloud and place it there.[/dim]")

    # ── slack / zoom (session-based — no config, just a one-time auth step) ────
    if slack_on:
        console.rule("Slack")
        console.print(
            "  Slack reads your signed-in [bold]Slack desktop app[/bold] session — no config needed.\n"
            "  After setup, run [cyan]sophonic auth slack[/cyan] to verify (approve the Keychain prompt)."
        )
    if zoom_on:
        console.rule("Zoom")
        console.print(
            "  Zoom reads your [bold]AI Companion meeting notes[/bold] via your zoom.us cookies.\n"
            "  Log in to zoom.us, then run "
            "[cyan]sophonic config set-secret ZOOM_COOKIES --stdin[/cyan] and paste the cookies."
        )

    # ── gitlab ──────────────────────────────────────────────────────────────
    if gitlab_on:
        console.rule("GitLab")
        ask_str("gitlab.url", "GitLab instance URL")
        ask_str("gitlab.default_project", "Default project (group/project)")
        ask_secret("GITLAB_TOKEN", "GitLab Personal Access Token (api scope)")

    # ── persist config.toml ───────────────────────────────────────────────────
    try:
        Config.model_validate(raw)
    except Exception as exc:
        console.print(f"[red]Configuration invalid, nothing written:[/red] {exc}")
        return
    config_io.write_raw(raw)
    console.print(f"\n[green]Wrote[/green] {config_io.config_file()}")

    # ── optional: run browser/OAuth auth flows now (terminal only) ─────────────
    console.rule("Authentication")
    from sophonic.cli import run_auth_google, run_auth_slack, run_auth_zoom

    if google_on and Confirm.ask("Run Google OAuth now?", default=False):
        run_auth_google()
    if slack_on and Confirm.ask("Log in to Slack now (opens a browser)?", default=False):
        run_auth_slack()
    if zoom_on and Confirm.ask("Log in to Zoom now (opens a browser)?", default=False):
        run_auth_zoom()

    console.print("\n[bold green]Setup complete.[/bold green] Run [cyan]sophonic doctor[/cyan] to verify.")
