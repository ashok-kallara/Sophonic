"""Tests for the sophonic skills loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from sophonic import skills


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_skill(tmp_path: Path, name: str, description: str, tools: list[str], body: str) -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True)
    content = f"---\nname: {name}\ndescription: \"{description}\"\ntools:\n"
    for t in tools:
        content += f"  - {t}\n"
    content += f"---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


# ── load_skill ────────────────────────────────────────────────────────────────

def test_load_skill_returns_meta(tmp_path):
    _make_skill(tmp_path, "gcal", "Calendar events", ["gcal_events_today"], "# GCal body")
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        meta = skills.load_skill("gcal")
    assert meta is not None
    assert meta.name == "gcal"
    assert meta.description == "Calendar events"
    assert meta.tools == ["gcal_events_today"]
    assert "GCal body" in meta.body


def test_load_skill_missing_returns_none(tmp_path):
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        meta = skills.load_skill("nonexistent")
    assert meta is None


def test_load_skill_user_override_wins(tmp_path):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    _make_skill(bundled, "gcal", "bundled description", ["gcal_events_today"], "bundled body")
    _make_skill(user, "gcal", "user description", ["gcal_events_today"], "user body")
    with patch.object(skills, "_bundled_skills_dir", return_value=bundled), \
         patch.object(skills, "_user_skills_dir", return_value=user):
        meta = skills.load_skill("gcal")
    assert meta is not None
    assert meta.description == "user description"
    assert "user body" in meta.body


# ── discover ──────────────────────────────────────────────────────────────────

def test_discover_returns_all_bundled(tmp_path):
    _make_skill(tmp_path, "gcal", "Calendar", ["gcal_events_today"], "body")
    _make_skill(tmp_path, "gmail", "Email", ["gmail_unread"], "body")
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        found = skills.discover()
    names = {s.name for s in found}
    assert "gcal" in names
    assert "gmail" in names


def test_discover_user_override_replaces_bundled(tmp_path):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    _make_skill(bundled, "gcal", "bundled", ["gcal_events_today"], "bundled")
    _make_skill(user, "gcal", "overridden", ["gcal_events_today"], "overridden")
    with patch.object(skills, "_bundled_skills_dir", return_value=bundled), \
         patch.object(skills, "_user_skills_dir", return_value=user):
        found = skills.discover()
    gcal_skills = [s for s in found if s.name == "gcal"]
    assert len(gcal_skills) == 1
    assert gcal_skills[0].description == "overridden"


# ── index ─────────────────────────────────────────────────────────────────────

def test_index_contains_name_and_description(tmp_path):
    _make_skill(tmp_path, "gcal", "Google Calendar events", ["gcal_events_today"], "body")
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        idx = skills.index()
    assert "gcal" in idx
    assert "Google Calendar events" in idx


def test_index_empty_when_no_skills(tmp_path):
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        idx = skills.index()
    assert idx == ""


def test_index_format(tmp_path):
    _make_skill(tmp_path, "gcal", "Calendar events", ["gcal_events_today"], "body")
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        idx = skills.index()
    assert "Available capabilities" in idx
    assert "- **gcal**: Calendar events" in idx


# ── skill_load ────────────────────────────────────────────────────────────────

def test_skill_load_returns_body(tmp_path):
    _make_skill(tmp_path, "gcal", "Calendar", ["gcal_events_today"], "# GCal\n\nUse this for calendar.")
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        result = skills.skill_load("gcal")
    assert result["name"] == "gcal"
    assert "GCal" in result["body"]


def test_skill_load_unknown_returns_error(tmp_path):
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        result = skills.skill_load("nonexistent")
    assert "error" in result


# ── template ──────────────────────────────────────────────────────────────────

def test_template_renders_variables(tmp_path):
    tpl_dir = tmp_path / "obsidian" / "templates"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "daily.md.j2").write_text("# DAILY {{ date }}\n#sophonic\n", encoding="utf-8")
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        result = skills.template("obsidian", "daily", date="2026-05-17")
    assert "DAILY 2026-05-17" in result
    assert "#sophonic" in result


def test_template_missing_raises(tmp_path):
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        with pytest.raises(FileNotFoundError):
            skills.template("obsidian", "nonexistent")


# ── validate ──────────────────────────────────────────────────────────────────

def test_validate_passes_when_all_tools_registered(tmp_path):
    _make_skill(tmp_path, "gcal", "Calendar", ["gcal_events_today", "gcal_events_range"], "body")
    registry: dict[str, Any] = {
        "gcal_events_today": lambda: None,
        "gcal_events_range": lambda: None,
    }
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        skills.validate(registry)  # should not raise


def test_validate_passes_when_skill_feature_disabled(tmp_path):
    """Skills with no registered tools (feature disabled) pass silently."""
    _make_skill(tmp_path, "gcal", "Calendar", ["gcal_events_today"], "body")
    registry: dict[str, Any] = {}  # gcal not loaded
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        skills.validate(registry)  # should not raise


def test_validate_raises_on_partial_registration(tmp_path):
    """If some but not all tools from a skill are registered, raise ValueError."""
    _make_skill(tmp_path, "gcal", "Calendar", ["gcal_events_today", "gcal_events_range"], "body")
    registry: dict[str, Any] = {
        "gcal_events_today": lambda: None,
        # gcal_events_range missing — partial registration
    }
    with patch.object(skills, "_bundled_skills_dir", return_value=tmp_path), \
         patch.object(skills, "_user_skills_dir", return_value=tmp_path / "nonexistent"):
        with pytest.raises(ValueError, match="gcal_events_range"):
            skills.validate(registry)
