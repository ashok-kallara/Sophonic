"""Akashic CLI — Typer app with feature-gated subcommands."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

app = typer.Typer(name="sophonic", help="Obsidian-native AI assistant")
console = Console()


# ── ask ───────────────────────────────────────────────────────────────────────

@app.command()
def ask(prompt: str = typer.Argument(..., help="Natural-language question or request")):
    """Ask Akashic anything — uses the full tool-use loop with Claude."""
    from sophonic.llm import ask as _ask
    console.print("[dim]Thinking...[/dim]")
    result = _ask(prompt)
    console.print(Markdown(result))


# ── today ─────────────────────────────────────────────────────────────────────

@app.command()
def today():
    """Show today's calendar, due tasks, and yesterday's incomplete tasks."""
    from sophonic.config import load_config
    from sophonic.tools.obsidian import incomplete_yesterday, list_tasks

    cfg = load_config().features

    if cfg.google:
        try:
            from sophonic.tools.gcal import events_today
            events = events_today()
            _print_events(events)
        except Exception as e:
            console.print(f"[yellow]Calendar unavailable:[/yellow] {e}")

    due = list_tasks(filter="due_today")
    _print_tasks("Due Today", due)

    overdue = incomplete_yesterday()
    _print_tasks("Incomplete from Yesterday", overdue)


def _print_events(events: list) -> None:
    if not events:
        console.print("[dim]No calendar events today.[/dim]")
        return
    t = Table(title="Calendar — Today", show_header=True)
    t.add_column("Time")
    t.add_column("Title")
    for e in events:
        t.add_row(str(e.get("start", ""))[:16], e.get("title", ""))
    console.print(t)


def _print_tasks(heading: str, tasks: list) -> None:
    if not tasks:
        console.print(f"[dim]{heading}: none[/dim]")
        return
    console.print(f"\n[bold]{heading}[/bold]")
    for t in tasks:
        console.print(f"  {t['text']}")


# ── daily ─────────────────────────────────────────────────────────────────────

@app.command()
def daily():
    """Print today's daily note (creates it if missing)."""
    from sophonic.tools.obsidian import get_daily_note
    console.print(Markdown(get_daily_note()))


# ── rollover ──────────────────────────────────────────────────────────────────

@app.command()
def rollover():
    """Copy yesterday's incomplete tasks into today's daily note."""
    from sophonic.tools.obsidian import roll_over
    result = roll_over()
    if result["rolled"]:
        console.print(f"[green]Rolled over {result['rolled']} task(s) from {result['from']} → {result['to']}[/green]")
        for t in result.get("tasks", []):
            console.print(f"  {t}")
    else:
        console.print(f"[dim]{result['message']}[/dim]")


# ── remind ────────────────────────────────────────────────────────────────────

@app.command()
def remind(phrase: str = typer.Argument(..., help="Natural-language reminder")):
    """Create a reminder in today's daily note. E.g. 'send report by Friday'."""
    from sophonic.tools.reminders import reminder_create
    result = reminder_create(phrase)
    console.print(f"[green]Added:[/green] {result['added']}")
    console.print(f"[dim]→ {result['file']}[/dim]")


# ── tasks ─────────────────────────────────────────────────────────────────────

@app.command()
def tasks(
    due: Optional[str] = typer.Option(None, "--due", help="Filter: today | overdue | YYYY-MM-DD"),
    overdue: bool = typer.Option(False, "--overdue", help="Show overdue tasks"),
    incomplete_yesterday: bool = typer.Option(False, "--incomplete-yesterday"),
):
    """List Obsidian tasks with optional filters."""
    from sophonic.tools.obsidian import incomplete_yesterday as iy, list_tasks

    if incomplete_yesterday:
        results = iy()
    elif overdue:
        results = list_tasks(filter="overdue")
    elif due == "today":
        results = list_tasks(filter="due_today")
    elif due:
        results = list_tasks(filter=f"due_before:{due}")
    else:
        results = list_tasks(filter="all")

    if not results:
        console.print("[dim]No matching tasks.[/dim]")
        return
    for t in results:
        console.print(f"  {t['text']}  [dim]{t.get('file','')}[/dim]")


# ── tool dispatch (registry passthrough — powers the MCP-free plugin) ──────────


def _plugin_registry() -> dict:
    """The full feature-gated tool registry plus skill_load, exactly as the MCP server exposes it."""
    from sophonic.tools import build_registry
    from sophonic import skills as _skills

    return {**build_registry(), "skill_load": _skills.skill_load}


@app.command("tools")
def tools_list():
    """List every available Sophonic tool as JSON (name + one-line description)."""
    reg = _plugin_registry()
    out = [
        {"name": name, "description": (fn.__doc__ or name).strip().split("\n")[0]}
        for name, fn in reg.items()
    ]
    typer.echo(json.dumps(out, indent=2, default=str))


@app.command("tool")
def tool_call(
    name: str = typer.Argument(..., help="Tool name, e.g. obsidian_list_tasks (see `sophonic tools`)"),
    args_json: str = typer.Option("{}", "--args-json", help="JSON object of keyword arguments"),
):
    """Invoke a single Sophonic tool by name and print its JSON result. Needs no API key."""
    reg = _plugin_registry()
    fn = reg.get(name)
    if fn is None:
        typer.echo(json.dumps({"error": f"Unknown tool: {name}", "available": sorted(reg)}, default=str))
        raise typer.Exit(1)
    try:
        args = json.loads(args_json)
        if not isinstance(args, dict):
            raise ValueError("--args-json must be a JSON object of keyword arguments")
        result = fn(**args)
    except Exception as exc:
        typer.echo(json.dumps({"error": str(exc)}, default=str))
        raise typer.Exit(1)
    typer.echo(json.dumps(result, indent=2, default=str))


# ── mail ──────────────────────────────────────────────────────────────────────

mail_app = typer.Typer(help="Gmail commands")
app.add_typer(mail_app, name="mail")


@mail_app.command("unread")
def mail_unread(max: int = typer.Option(20, "--max")):
    """Show unread Gmail messages."""
    from sophonic.config import load_config
    if not load_config().features.google:
        console.print("[red]Google integration is disabled in config.[/red]")
        raise typer.Exit(1)
    from sophonic.tools.gmail import unread
    msgs = unread(max=max)
    for m in msgs:
        console.print(f"[bold]{m['subject']}[/bold]  [dim]{m['from']}[/dim]")
        console.print(f"  {m['snippet'][:80]}")


# ── slack ─────────────────────────────────────────────────────────────────────

slack_app = typer.Typer(help="Slack commands")
app.add_typer(slack_app, name="slack")


@slack_app.command("unread")
def slack_unread():
    """Show unread Slack messages."""
    from sophonic.config import load_config
    if not load_config().features.slack:
        console.print("[red]Slack integration is disabled in config.[/red]")
        raise typer.Exit(1)
    from sophonic.tools.slack_local import unread
    items = unread()
    for item in items:
        if "needs_auth" in item:
            console.print(f"[yellow]Not authenticated. Run:[/yellow] {item['run']}")
            return
        console.print(f"  {item.get('channel', item)}")


@slack_app.command("search")
def slack_search(query: str = typer.Argument(...)):
    """Search Slack."""
    from sophonic.tools.slack_local import search
    items = search(query)
    for item in items:
        if "needs_auth" in item:
            console.print(f"[yellow]Not authenticated. Run:[/yellow] {item['run']}")
            return
        console.print(f"  {item.get('text', item)}")


# ── zoom ──────────────────────────────────────────────────────────────────────

zoom_app = typer.Typer(help="Zoom commands")
app.add_typer(zoom_app, name="zoom")


@zoom_app.command("notes")
def zoom_notes_cmd(limit: int = typer.Option(20, "--limit")):
    """List recent Zoom AI meeting notes."""
    from sophonic.config import load_config
    if not load_config().features.zoom:
        console.print("[red]Zoom integration is disabled in config.[/red]")
        raise typer.Exit(1)
    from sophonic.tools.zoom import notes
    items = notes(limit)
    for item in items:
        if "needs_auth" in item:
            console.print(f"[yellow]Not authenticated. Run:[/yellow] {item['run']}")
            return
        if "message" in item:
            console.print(f"[dim]{item['message']}[/dim]")
            return
        console.print(f"  {item.get('date') or '':10}  {item.get('meeting', item.get('title',''))}  [dim]{item.get('id','')}[/dim]")


@zoom_app.command("save")
def zoom_save(
    doc_id: str = typer.Argument(..., help="Note id from 'sophonic zoom notes'"),
    title: Optional[str] = typer.Option(None, "--title"),
):
    """Fetch a Zoom AI meeting note and file it as an Obsidian meeting note."""
    from sophonic.config import load_config
    if not load_config().features.zoom:
        console.print("[red]Zoom integration is disabled in config.[/red]")
        raise typer.Exit(1)
    from sophonic.tools.zoom import save_note
    result = save_note(doc_id, title=title)
    if "needs_auth" in result:
        console.print(f"[yellow]Not authenticated. Run:[/yellow] {result['run']}")
        return
    if "error" in result:
        console.print(f"[red]Error:[/red] {result['error']}")
        return
    console.print(f"[green]Saved:[/green] {result['saved']}")
    if "backlinked_in" in result:
        console.print(f"[dim]Backlinked in:[/dim] {result['backlinked_in']}")


# ── auth ──────────────────────────────────────────────────────────────────────

auth_app = typer.Typer(help="Authentication commands")
app.add_typer(auth_app, name="auth")


def run_auth_google() -> None:
    """Run the Google OAuth flow (opens a browser)."""
    from sophonic.google_auth import get_credentials
    get_credentials()
    console.print("[green]Google authentication successful.[/green]")


def run_auth_slack() -> None:
    """Verify Slack access by reading the desktop app's session (no browser)."""
    from sophonic.tools import slack_local

    try:
        token, d_cookie = slack_local._get_credentials()
    except slack_local.SlackAuthError as exc:
        console.print(f"[red]Slack auth failed:[/red] {exc}")
        console.print("[dim]Make sure the Slack desktop app is installed and signed in.[/dim]")
        raise typer.Exit(1)
    identity = slack_local._api("auth.test", {}, token, d_cookie)
    who = identity.get("user", "?")
    team = identity.get("team", "?")
    console.print(f"[green]Slack OK[/green] — signed in as [bold]{who}[/bold] in [bold]{team}[/bold].")


def run_auth_zoom() -> None:
    """Zoom uses pasted session cookies (browser login can't be automated in Island)."""
    import os
    if os.environ.get("ZOOM_COOKIES"):
        console.print("[green]Zoom cookies are set.[/green] Try: sophonic zoom transcripts")
        return
    console.print(
        "Zoom needs your web session cookies (Island blocks browser automation).\n"
        "1. Log in to [cyan]https://zoom.us[/cyan] in your browser.\n"
        "2. Copy the zoom.us cookies (as 'name=value; name2=value2').\n"
        "3. Run: [cyan]sophonic config set-secret ZOOM_COOKIES --stdin[/cyan] and paste them."
    )


@auth_app.command("google")
def auth_google():
    """Run Google OAuth flow (opens browser)."""
    run_auth_google()


@auth_app.command("slack")
def auth_slack():
    """Open browser to log in to Slack (saves session for future headless use)."""
    run_auth_slack()


@auth_app.command("zoom")
def auth_zoom():
    """Open browser to log in to Zoom (saves session for future headless use)."""
    run_auth_zoom()


# ── init (interactive wizard) ───────────────────────────────────────────────────

@app.command()
def init():
    """Interactive setup wizard — configure the vault, features, LLM, and integrations."""
    from sophonic.wizard import run_init
    run_init()


# ── config (non-interactive; powers the plugin's setup skill) ────────────────────

config_app = typer.Typer(help="View and edit configuration (~/.sophonic/config.toml + .env)")
app.add_typer(config_app, name="config")


def _dig(data: dict, dotted: str):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


@config_app.command("show")
def config_show(as_json: bool = typer.Option(True, "--json/--no-json", help="Output JSON (default) or a table")):
    """Print the effective configuration with secrets redacted."""
    from sophonic import config_io
    data = config_io.redacted()
    data["_secrets_in_env"] = config_io.env_secret_names()
    if as_json:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        console.print(data)


@config_app.command("get")
def config_get(key: str = typer.Argument(..., help="Dotted key, e.g. llm.model")):
    """Print a single config value (from the effective configuration)."""
    from sophonic.config import load_config
    value, found = _dig(load_config().model_dump(mode="json"), key)
    if not found:
        typer.echo(json.dumps({"error": f"Unknown config key: {key}"}))
        raise typer.Exit(1)
    typer.echo(json.dumps(value, default=str))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dotted key, e.g. llm.model or features.gitlab"),
    value: str = typer.Argument(..., help="Value (bools: true/false, ints coerced, lists comma-separated)"),
):
    """Set a config key in config.toml (validated before writing)."""
    from sophonic import config_io
    try:
        coerced = config_io.set_key(key, value)
    except Exception as exc:
        typer.echo(json.dumps({"error": str(exc)}, default=str))
        raise typer.Exit(1)
    typer.echo(json.dumps({"set": key, "value": coerced}, default=str))


@config_app.command("unset")
def config_unset(key: str = typer.Argument(..., help="Dotted key to remove")):
    """Remove a config key from config.toml (reverts it to its default)."""
    from sophonic import config_io
    try:
        removed = config_io.unset_key(key)
    except Exception as exc:
        typer.echo(json.dumps({"error": str(exc)}, default=str))
        raise typer.Exit(1)
    typer.echo(json.dumps({"unset": key, "removed": removed}))


@config_app.command("set-secret")
def config_set_secret(
    name: str = typer.Argument(..., help="Environment variable name, e.g. ANTHROPIC_API_KEY"),
    value: Optional[str] = typer.Option(None, "--value", help="Secret value (avoid — lands in shell history)"),
    stdin: bool = typer.Option(False, "--stdin", help="Read the secret from stdin (recommended)"),
):
    """Store a secret in ~/.sophonic/.env (chmod 0600). Prefer --stdin to keep it out of history."""
    import sys
    from sophonic import config_io

    if stdin:
        secret = sys.stdin.readline().rstrip("\n")
    elif value is not None:
        secret = value
    else:
        typer.echo(json.dumps({"error": "Provide --value or --stdin"}))
        raise typer.Exit(1)
    if not secret:
        typer.echo(json.dumps({"error": "Empty secret"}))
        raise typer.Exit(1)
    config_io.set_secret(name, secret)
    typer.echo(json.dumps({"set_secret": name, "file": str(config_io.env_file())}))


@config_app.command("path")
def config_path():
    """Print the config.toml and .env paths."""
    from sophonic import config_io
    typer.echo(json.dumps({"config": str(config_io.config_file()), "env": str(config_io.env_file())}))


# ── doctor (status check; the plugin's entry point) ──────────────────────────────

@app.command()
def doctor():
    """Report configuration/auth status per integration as JSON, with fix commands for gaps."""
    typer.echo(json.dumps(_doctor(), indent=2, default=str))


def _doctor() -> dict:
    import os
    from pathlib import Path
    from sophonic.config import config_dir, load_config

    cfg = load_config()
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, fix: str = "") -> None:
        entry = {"name": name, "ok": ok, "detail": detail}
        if not ok and fix:
            entry["fix"] = fix
        checks.append(entry)

    # vault
    vault = Path(cfg.vault.path)
    add("vault", vault.is_dir(), f"vault.path = {vault}",
        f"sophonic config set vault.path <path>  (and create the directory)")

    # llm
    from sophonic.config import LLM_API_KEY_ENV, llm_api_key_envs, resolve_llm_api_key

    key_present = bool(resolve_llm_api_key(cfg.llm.provider))
    key_envs = " or ".join(llm_api_key_envs(cfg.llm.provider))
    add("llm", key_present,
        f"provider={cfg.llm.provider} model={cfg.llm.model} key from {key_envs}",
        f"sophonic config set-secret {LLM_API_KEY_ENV} --stdin")
    # a LiteLLM proxy needs api_base, or the client silently falls back to api.openai.com
    if cfg.llm.provider == "litellm":
        add("llm.api_base", bool(cfg.llm.api_base), f"api_base = {cfg.llm.api_base or '(unset)'}",
            "sophonic config set llm.api_base <litellm-proxy-url>")

    # google
    if cfg.features.google:
        secret = Path(str(cfg.google.client_secret_file).replace("~", str(Path.home())))
        add("google.client_secret", secret.exists(), f"{secret}",
            "Download an OAuth desktop client JSON and save it there")
        token = config_dir() / "tokens" / "google.json"
        add("google.auth", token.exists(), f"token: {token}", "sophonic auth google")

    # slack — reads the desktop app session (no browser)
    if cfg.features.slack:
        from sophonic.tools import slack_local
        try:
            token, d_cookie = slack_local._get_credentials()
            ok = bool(slack_local._api("auth.test", {}, token, d_cookie).get("ok"))
            detail = "Slack desktop app session readable + auth.test ok" if ok else "auth.test failed"
        except Exception as exc:
            ok, detail = False, str(exc)
        add("slack", ok, detail,
            "Sign in to the Slack desktop app; then `sophonic auth slack` (approve the Keychain prompt)")

    # zoom — uses pasted web session cookies (no browser login)
    if cfg.features.zoom:
        has_cookies = bool(os.environ.get("ZOOM_COOKIES"))
        add("zoom", has_cookies, "ZOOM_COOKIES " + ("set" if has_cookies else "missing"),
            "sophonic config set-secret ZOOM_COOKIES --stdin  (paste your zoom.us cookies)")

    # gitlab
    if cfg.features.gitlab:
        token_present = bool(cfg.gitlab.token or os.environ.get("GITLAB_TOKEN"))
        ok = bool(cfg.gitlab.url) and token_present
        add("gitlab", ok, f"url={cfg.gitlab.url or '(unset)'} token={'set' if token_present else 'missing'}",
            "sophonic config set gitlab.url <url> ; sophonic config set-secret GITLAB_TOKEN --stdin")

    return {"ok": all(c["ok"] for c in checks), "checks": checks}
