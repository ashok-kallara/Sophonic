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


@freeze_time("2026-05-02")
def test_incomplete_yesterday_finds_tasks(use_fixture_vault):
    from sophonic.tools.obsidian import add_task, incomplete_yesterday
    yesterday = date(2026, 5, 1)
    add_task("Overdue item", due=date(2026, 5, 1), note_date=yesterday)
    results = incomplete_yesterday()
    assert any("Overdue item" in r["text"] for r in results)


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
