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

app = typer.Typer(name="akashic", help="Obsidian-native AI assistant")
console = Console()


# ── ask ───────────────────────────────────────────────────────────────────────

@app.command()
def ask(prompt: str = typer.Argument(..., help="Natural-language question or request")):
    """Ask Akashic anything — uses the full tool-use loop with Claude."""
    from akashic.llm import ask as _ask
    console.print("[dim]Thinking...[/dim]")
    result = _ask(prompt)
    console.print(Markdown(result))


# ── today ─────────────────────────────────────────────────────────────────────

@app.command()
def today():
    """Show today's calendar, due tasks, and yesterday's incomplete tasks."""
    from akashic.config import load_config
    from akashic.tools.obsidian import incomplete_yesterday, list_tasks

    cfg = load_config().features

    if cfg.google:
        try:
            from akashic.tools.gcal import events_today
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
    from akashic.tools.obsidian import get_daily_note
    console.print(Markdown(get_daily_note()))


# ── rollover ──────────────────────────────────────────────────────────────────

@app.command()
def rollover():
    """Copy yesterday's incomplete tasks into today's daily note."""
    from akashic.tools.obsidian import roll_over
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
    from akashic.tools.reminders import reminder_create
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
    from akashic.tools.obsidian import incomplete_yesterday as iy, list_tasks

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


# ── mail ──────────────────────────────────────────────────────────────────────

mail_app = typer.Typer(help="Gmail commands")
app.add_typer(mail_app, name="mail")


@mail_app.command("unread")
def mail_unread(max: int = typer.Option(20, "--max")):
    """Show unread Gmail messages."""
    from akashic.config import load_config
    if not load_config().features.google:
        console.print("[red]Google integration is disabled in config.[/red]")
        raise typer.Exit(1)
    from akashic.tools.gmail import unread
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
    from akashic.config import load_config
    if not load_config().features.slack:
        console.print("[red]Slack integration is disabled in config.[/red]")
        raise typer.Exit(1)
    from akashic.tools.slack_web import unread
    items = unread()
    for item in items:
        if "needs_auth" in item:
            console.print(f"[yellow]Not authenticated. Run:[/yellow] {item['run']}")
            return
        console.print(f"  {item.get('channel', item)}")


@slack_app.command("search")
def slack_search(query: str = typer.Argument(...)):
    """Search Slack."""
    from akashic.tools.slack_web import search
    items = search(query)
    for item in items:
        console.print(f"  {item.get('text', item)}")


# ── zoom ──────────────────────────────────────────────────────────────────────

zoom_app = typer.Typer(help="Zoom commands")
app.add_typer(zoom_app, name="zoom")


@zoom_app.command("transcripts")
def zoom_transcripts(since: str = typer.Option("7d", "--since")):
    """List recent Zoom recordings."""
    from akashic.config import load_config
    if not load_config().features.zoom:
        console.print("[red]Zoom integration is disabled in config.[/red]")
        raise typer.Exit(1)
    days = int(since.rstrip("d"))
    from akashic.tools.zoom import transcripts
    items = transcripts(since_days=days)
    for item in items:
        if "needs_auth" in item:
            console.print(f"[yellow]Not authenticated. Run:[/yellow] {item['run']}")
            return
        console.print(f"  {item.get('date', '')}  {item.get('title', '')}  [dim]{item.get('link', '')}[/dim]")


@zoom_app.command("save")
def zoom_save(
    url: str = typer.Argument(..., help="Recording URL from 'akashic zoom transcripts'"),
    title: Optional[str] = typer.Option(None, "--title"),
    date: Optional[str] = typer.Option(None, "--date", help="YYYY-MM-DD"),
):
    """Fetch a Zoom transcript and file it as an Obsidian meeting note."""
    from akashic.config import load_config
    if not load_config().features.zoom:
        console.print("[red]Zoom integration is disabled in config.[/red]")
        raise typer.Exit(1)
    from akashic.tools.zoom import save_transcript
    result = save_transcript(url, title=title, recorded_date=date)
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


@auth_app.command("google")
def auth_google():
    """Run Google OAuth flow (opens browser)."""
    from akashic.google_auth import get_credentials
    creds = get_credentials()
    console.print("[green]Google authentication successful.[/green]")


@auth_app.command("slack")
def auth_slack():
    """Open browser to log in to Slack (saves session for future headless use)."""
    from akashic.browser import open_auth_browser
    asyncio.get_event_loop().run_until_complete(
        open_auth_browser("slack", "https://app.slack.com")
    )
    console.print("[green]Slack session saved.[/green]")


@auth_app.command("zoom")
def auth_zoom():
    """Open browser to log in to Zoom (saves session for future headless use)."""
    from akashic.browser import open_auth_browser
    asyncio.get_event_loop().run_until_complete(
        open_auth_browser("zoom", "https://zoom.us/signin")
    )
    console.print("[green]Zoom session saved.[/green]")
