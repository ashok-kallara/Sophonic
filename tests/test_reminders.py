"""Tests for reminder creation."""

from datetime import date

import pytest
from freezegun import freeze_time


@freeze_time("2026-05-02")
def test_reminder_tomorrow(use_fixture_vault):
    from sophonic.tools.reminders import reminder_create
    result = reminder_create("send the report tomorrow")
    assert "📅 2026-05-03" in result["added"]


@freeze_time("2026-05-02")
def test_reminder_next_friday(use_fixture_vault):
    from sophonic.tools.reminders import reminder_create
    result = reminder_create("submit expense report next Friday")
    assert "📅" in result["added"]
    due = result["added"].split("📅")[1].strip()[:10]
    d = date.fromisoformat(due)
    assert d.weekday() == 4  # Friday
    assert d > date(2026, 5, 2)


@freeze_time("2026-05-02")
def test_reminder_in_days(use_fixture_vault):
    from sophonic.tools.reminders import reminder_create
    result = reminder_create("review PR in 3 days")
    assert "📅 2026-05-05" in result["added"]


@freeze_time("2026-05-02")
def test_reminder_strips_preamble(use_fixture_vault):
    from sophonic.tools.reminders import reminder_create
    result = reminder_create("remind me to call dentist tomorrow")
    assert "call dentist" in result["added"].lower()
    assert "remind me to" not in result["added"].lower()


@freeze_time("2026-05-02")
def test_reminder_with_tags(use_fixture_vault):
    from sophonic.tools.reminders import reminder_create
    result = reminder_create("pay rent tomorrow", tags=["personal/finance"])
    assert "#personal/finance" in result["added"]


@freeze_time("2026-05-02")
def test_reminder_writes_to_daily_note(use_fixture_vault):
    from sophonic.tools.obsidian import ensure_daily_note
    from sophonic.tools.reminders import reminder_create
    reminder_create("buy groceries tomorrow")
    content = ensure_daily_note().read_text()
    assert "buy groceries" in content.lower()
