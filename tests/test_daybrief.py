"""Tests for the start_day orchestrator (composition, merge, dedupe, error isolation)."""

from datetime import date

import pytest
from freezegun import freeze_time


@pytest.fixture
def stub_sources(monkeypatch):
    """Stub every external source + the calendar fetch so start_day stays offline."""
    import sophonic.tools.obsidian as obs
    from sophonic.tools import gtasks, slack_local, zoom
    from sophonic import llm

    monkeypatch.setattr(obs, "_today_events", lambda d: None)  # no calendar/network
    monkeypatch.setattr(zoom, "action_items", lambda **kw: {
        "count": 2, "range": {"start": "x", "end": "x"}, "meetings_scanned": 1,
        "action_items": [], "dry_run": kw.get("dry_run", False),
    })
    monkeypatch.setattr(gtasks, "list_open_tasks", lambda **kw: [
        {"id": "t1", "title": "Ship it", "list": "Work", "due": date(2026, 8, 5), "notes": ""},
    ])
    monkeypatch.setattr(slack_local, "unread_digest", lambda **kw: {
        "actionable": [{
            "channel": "@Alice", "type": "im", "mentions": 0,
            "latest": "ping you", "permalink": "https://slack/D1", "messages": [],
        }],
        "informational": [{"channel": "#general", "mentions": 0,
                           "messages": [{"user": "Bob", "text": "hi team"}]}],
    })
    monkeypatch.setattr(llm, "summarize", lambda *a, **k: "- **#general** — casual chatter")


@freeze_time("2026-08-04")
def test_start_day_merges_all_sources(use_fixture_vault, stub_sources):
    from sophonic import daybrief
    from sophonic.tools.obsidian import get_daily_note

    result = daybrief.start_day()
    assert result["tasks_added"] == {"zoom": 2, "gtasks": 1, "slack": 1}

    note = get_daily_note()
    # Google Task merged with list ref, due date, and #gtask tag.
    assert "Ship it (Google Tasks: Work)" in note
    assert "📅 2026-08-05" in note
    assert "#gtask" in note
    # Slack DM became a reply task with the permalink and #slack tag.
    assert "Reply to @Alice: ping you https://slack/D1" in note
    assert "#slack" in note
    # Informational channel summarized into a refreshable ## Slack section.
    assert "## Slack" in note
    assert "casual chatter" in note

    ok = {s["name"] for s in result["sources"] if s["ok"]}
    assert {"daily_note", "zoom", "gtasks", "slack"} <= ok


@freeze_time("2026-08-04")
def test_start_day_is_idempotent(use_fixture_vault, stub_sources):
    from sophonic import daybrief
    from sophonic.tools.obsidian import get_daily_note

    daybrief.start_day()
    again = daybrief.start_day()
    assert again["tasks_added"]["gtasks"] == 0   # deduped
    assert again["tasks_added"]["slack"] == 0     # deduped by conversation
    note = get_daily_note()
    assert note.count("Ship it (Google Tasks: Work)") == 1
    assert note.count("Reply to @Alice") == 1
    assert note.count("## Slack") == 1            # section replaced, not stacked


@freeze_time("2026-08-04")
def test_start_day_dry_run_writes_nothing(use_fixture_vault, stub_sources):
    from sophonic import daybrief
    from sophonic.tools.obsidian import get_daily_note

    result = daybrief.start_day(dry_run=True)
    assert result["tasks_added"]["gtasks"] == 1   # would-add count
    note = get_daily_note()
    assert "Ship it (Google Tasks: Work)" not in note
    assert "## Slack" not in note


@freeze_time("2026-08-04")
def test_start_day_isolates_failing_source(use_fixture_vault, stub_sources, monkeypatch):
    from sophonic import daybrief
    from sophonic.tools import gtasks
    from sophonic.tools.obsidian import get_daily_note

    # Google Tasks unauthenticated (missing scope) — must not abort the brief.
    monkeypatch.setattr(gtasks, "list_open_tasks", lambda **kw: {
        "needs_auth": True, "detail": "needs tasks scope", "run": "sophonic auth google",
    })
    result = daybrief.start_day()

    gt = next(s for s in result["sources"] if s["name"] == "gtasks")
    assert gt["ok"] is False and "run" in gt
    assert result["tasks_added"]["gtasks"] == 0
    # Slack still ran and merged.
    assert result["tasks_added"]["slack"] == 1
    assert "Reply to @Alice" in get_daily_note()


@freeze_time("2026-08-04")
def test_start_day_skip_flags(use_fixture_vault, stub_sources):
    from sophonic import daybrief
    from sophonic.tools.obsidian import get_daily_note

    result = daybrief.start_day(skip_tasks=True, skip_slack=True)
    assert result["tasks_added"]["gtasks"] == 0
    assert result["tasks_added"]["slack"] == 0
    note = get_daily_note()
    assert "Ship it (Google Tasks: Work)" not in note
    assert "## Slack" not in note
