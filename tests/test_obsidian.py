"""Tests for Obsidian vault operations."""

from datetime import date
from pathlib import Path

import pytest
from freezegun import freeze_time


@freeze_time("2026-05-02")
def test_ensure_daily_note_creates_file(use_fixture_vault):
    from sophonic.tools.obsidian import ensure_daily_note
    path = ensure_daily_note()
    assert path.exists()
    assert "DAILY-2026-05-02" in path.name
    content = path.read_text()
    assert "## Tasks" in content
    assert "## Notes" in content
    assert "#sophonic" in content


@freeze_time("2026-05-02")
def test_ensure_daily_note_idempotent(use_fixture_vault):
    from sophonic.tools.obsidian import ensure_daily_note
    path1 = ensure_daily_note()
    path1.write_text("custom content")
    path2 = ensure_daily_note()
    assert path2.read_text() == "custom content"


@freeze_time("2026-05-02")
def test_add_task_appears_in_daily_note(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, ensure_daily_note
    result = add_task("Buy milk", due=date(2026, 5, 3))
    assert "Buy milk" in result["added"]
    assert "📅 2026-05-03" in result["added"]
    content = ensure_daily_note().read_text()
    assert "Buy milk" in content


@freeze_time("2026-05-02")
def test_add_task_under_tasks_heading(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, ensure_daily_note
    add_task("Write report", due=date(2026, 5, 5))
    content = ensure_daily_note().read_text()
    tasks_idx = content.index("## Tasks")
    notes_idx = content.index("## Notes")
    task_idx = content.index("Write report")
    assert tasks_idx < task_idx < notes_idx


@freeze_time("2026-05-02")
def test_add_task_with_priority(use_fixture_vault):
    from sophonic.tools.obsidian import add_task
    result = add_task("Urgent task", due=date(2026, 5, 2), priority="high")
    assert "⏫" in result["added"]


@freeze_time("2026-05-02")
def test_list_tasks_due_today(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, list_tasks
    add_task("Task A", due=date(2026, 5, 2))
    add_task("Task B", due=date(2026, 5, 3))
    results = list_tasks(filter="due_today")
    texts = [r["text"] for r in results]
    assert any("Task A" in t for t in texts)
    assert not any("Task B" in t for t in texts)


@freeze_time("2026-05-02")
def test_list_tasks_overdue(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, list_tasks
    add_task("Old task", due=date(2026, 4, 30), note_date=date(2026, 4, 30))
    results = list_tasks(filter="overdue")
    assert any("Old task" in r["text"] for r in results)


@freeze_time("2026-05-02")
def test_complete_task(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, complete_task, ensure_daily_note
    add_task("Finish slides", due=date(2026, 5, 2))
    note = ensure_daily_note()
    content = note.read_text()
    task_line = next(l for l in content.splitlines() if "Finish slides" in l)
    rel_path = str(note.relative_to(use_fixture_vault))
    result = complete_task(rel_path, task_line)
    assert "completed" in result
    updated = note.read_text()
    assert "- [x]" in updated
    assert "✅ 2026-05-02" in updated


@freeze_time("2026-05-02")
def test_rollover_copies_incomplete(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, ensure_daily_note, roll_over
    # Create yesterday's note with one task
    yesterday = date(2026, 5, 1)
    add_task("Yesterday's task", note_date=yesterday)

    result = roll_over(from_date=yesterday, to_date=date(2026, 5, 2))
    assert result["rolled"] == 1
    today_content = ensure_daily_note(date(2026, 5, 2)).read_text()
    assert "Yesterday's task" in today_content


@freeze_time("2026-05-02")
def test_rollover_is_idempotent(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, roll_over
    yesterday = date(2026, 5, 1)
    add_task("Same task", note_date=yesterday)
    roll_over(from_date=yesterday, to_date=date(2026, 5, 2))
    result2 = roll_over(from_date=yesterday, to_date=date(2026, 5, 2))
    assert result2["rolled"] == 0


@freeze_time("2026-05-05")
def test_rollover_uses_latest_prior_note_across_gap(use_fixture_vault):
    """No note yesterday, but one two days back → roll from the last available day."""
    from sophonic.tools.obsidian import add_task, ensure_daily_note, roll_over

    add_task("Gap-day task", note_date=date(2026, 5, 3))  # 2 days before today; no 5/4 note

    result = roll_over()  # default: today = 2026-05-05, no from_date
    assert result["rolled"] == 1
    assert result["from"] == "2026-05-03"
    assert result["to"] == "2026-05-05"
    assert "Gap-day task" in ensure_daily_note(date(2026, 5, 5)).read_text()


@freeze_time("2026-05-05")
def test_rollover_picks_most_recent_of_several(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, roll_over

    add_task("Older", note_date=date(2026, 5, 1))
    add_task("Newer", note_date=date(2026, 5, 3))
    result = roll_over()
    assert result["from"] == "2026-05-03"   # most recent prior note wins
    assert result["tasks"] == ["- [ ] Newer"]


@freeze_time("2026-05-05")
def test_rollover_no_prior_note(use_fixture_vault):
    from sophonic.tools.obsidian import roll_over
    result = roll_over()
    assert result["rolled"] == 0
    assert "No previous daily note" in result["message"]


@freeze_time("2026-05-02")
def test_incomplete_yesterday_finds_tasks(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, incomplete_yesterday
    yesterday = date(2026, 5, 1)
    add_task("Overdue item", due=date(2026, 5, 1), note_date=yesterday)
    results = incomplete_yesterday()
    assert any("Overdue item" in r["text"] for r in results)


@freeze_time("2026-05-02")
def test_build_daily_note_enriches(use_fixture_vault, monkeypatch):
    import sophonic.tools.obsidian as obs

    # Stub the calendar so tests need no Google auth / network.
    monkeypatch.setattr(obs, "_today_events", lambda d: [
        {"title": "Standup", "start": "2026-05-02T09:00:00-04:00", "location": None},
    ])
    # Yesterday has an incomplete task to roll forward.
    obs.add_task("Carry me", note_date=date(2026, 5, 1))
    # A task due today lives in a different note.
    obs.add_task("Ship it", due=date(2026, 5, 2), note_date=date(2026, 4, 20))

    result = obs.build_daily_note()
    assert result["created"] is True

    content = obs.get_daily_note()
    assert "## Schedule" in content
    assert "09:00 — Standup" in content
    assert "Carry me" in content            # rolled over as a live checkbox
    assert "## Due Today" in content
    assert "Ship it" in content             # referenced in the agenda
    assert "DAILY-2026-04-20]]" in content   # backlink to its home note (folder per config)


@freeze_time("2026-05-02")
def test_build_daily_note_shows_placeholder_when_no_events(use_fixture_vault, monkeypatch):
    import sophonic.tools.obsidian as obs
    monkeypatch.setattr(obs, "_today_events", lambda d: [])
    obs.build_daily_note()
    content = obs.get_daily_note()
    assert "## Schedule" in content
    assert "_No events_" in content


@freeze_time("2026-05-02")
def test_build_daily_note_omits_schedule_when_google_off(use_fixture_vault, monkeypatch):
    import sophonic.tools.obsidian as obs
    monkeypatch.setattr(obs, "_today_events", lambda d: None)  # Google disabled
    obs.build_daily_note()
    assert "## Schedule" not in obs.get_daily_note()


@freeze_time("2026-05-02")
def test_build_daily_note_idempotent(use_fixture_vault, monkeypatch):
    import sophonic.tools.obsidian as obs
    monkeypatch.setattr(obs, "_today_events", lambda d: [])
    obs.build_daily_note()
    path = obs.daily_note_path()
    path.write_text("custom content")
    result = obs.build_daily_note()
    assert result["created"] is False
    assert path.read_text() == "custom content"


@freeze_time("2026-05-02")
def test_upsert_section_inserts_then_replaces(use_fixture_vault):
    from sophonic.tools.obsidian import ensure_daily_note, upsert_section

    ensure_daily_note()  # bare template with ## Tasks and ## Notes
    upsert_section("Slack", "- #general — 3 unread")
    content = ensure_daily_note().read_text()
    assert "## Slack" in content
    assert "#general — 3 unread" in content

    # A second call replaces the block rather than stacking a second heading.
    upsert_section("Slack", "- #random — 1 unread")
    content = ensure_daily_note().read_text()
    assert content.count("## Slack") == 1
    assert "#random — 1 unread" in content
    assert "#general — 3 unread" not in content


@freeze_time("2026-05-02")
def test_upsert_section_preserves_following_sections(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, ensure_daily_note, upsert_section

    add_task("Keep me", note_date=None)  # lands under ## Tasks
    upsert_section("Tasks", "- [ ] Replaced task")
    content = ensure_daily_note().read_text()
    assert "Replaced task" in content
    assert "Keep me" not in content   # section body was replaced
    assert "## Notes" in content      # following section survived


@freeze_time("2026-05-02")
def test_add_grouped_tasks_groups_and_dedupes(use_fixture_vault):
    from sophonic.tools.obsidian import add_grouped_tasks, ensure_daily_note

    ensure_daily_note()
    add_grouped_tasks("Meeting Action Items", [
        {"heading": "[Standup — 2026-05-02](https://z/A)", "items": ["Do A", "Do B"]},
        {"heading": "1:1 — 2026-05-02", "items": ["Do C"]},
    ], tags=["zoom"])
    content = ensure_daily_note().read_text()

    assert "## Meeting Action Items" in content
    assert "### [Standup — 2026-05-02](https://z/A)" in content
    assert "- [ ] Do A #zoom" in content
    assert "- [ ] Do B #zoom" in content
    assert "### 1:1 — 2026-05-02" in content
    assert "- [ ] Do C #zoom" in content
    # Section is placed before ## Notes.
    assert content.index("## Meeting Action Items") < content.index("## Notes")

    # Re-run: existing items are not duplicated; a new item lands under its meeting.
    add_grouped_tasks("Meeting Action Items", [
        {"heading": "[Standup — 2026-05-02](https://z/A)", "items": ["Do A", "Do D"]},
    ], tags=["zoom"])
    content = ensure_daily_note().read_text()
    assert content.count("- [ ] Do A #zoom") == 1
    assert "- [ ] Do D #zoom" in content
    assert content.count("### [Standup — 2026-05-02](https://z/A)") == 1


@freeze_time("2026-05-02")
def test_add_grouped_tasks_preserves_checked_items(use_fixture_vault):
    from sophonic.tools.obsidian import add_grouped_tasks, ensure_daily_note

    ensure_daily_note()
    add_grouped_tasks("Meeting Action Items", [{"heading": "M — 2026-05-02", "items": ["Task X"]}])
    note = ensure_daily_note()
    # User checks it off.
    note.write_text(note.read_text().replace("- [ ] Task X", "- [x] Task X ✅ 2026-05-02"))
    # Re-run must not re-add the (now completed) item.
    add_grouped_tasks("Meeting Action Items", [{"heading": "M — 2026-05-02", "items": ["Task X"]}])
    content = note.read_text()
    assert content.count("Task X") == 1
    assert "- [x] Task X" in content


def test_read_write_note(use_fixture_vault):
    from sophonic.tools.obsidian import read_note, write_note
    write_note("Test/note.md", "# Hello\n\nWorld")
    content = read_note("Test/note.md")
    assert "Hello" in content


def test_search_vault(use_fixture_vault):
    from sophonic.tools.obsidian import search_vault, write_note
    write_note("Search/target.md", "The quick brown fox")
    results = search_vault("quick brown")
    assert any("quick brown" in r["line"] for r in results)
