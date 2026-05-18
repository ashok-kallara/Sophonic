"""Tests for LLM tool schema generation."""

from datetime import date
from typing import Optional


def sample_fn(
    text: str,
    count: int,
    flag: bool,
    ratio: float,
    due: date | None,
    tags: list[str] | None,
    optional_str: str | None = None,
) -> dict:
    """Sample tool for schema testing."""
    ...


def test_schema_types():
    from sophonic.llm import _build_tools

    tools = _build_tools({"sample": sample_fn})
    assert len(tools) == 1
    schema = tools[0]["input_schema"]
    props = schema["properties"]

    assert props["text"]["type"] == "string"
    assert props["count"]["type"] == "integer"
    assert props["flag"]["type"] == "boolean"
    assert props["ratio"]["type"] == "number"
    assert props["due"]["type"] == "string"  # date → string
    assert props["tags"]["type"] == "array"
    assert props["tags"]["items"]["type"] == "string"


def test_schema_required_vs_optional():
    from sophonic.llm import _build_tools

    tools = _build_tools({"sample": sample_fn})
    schema = tools[0]["input_schema"]
    required = schema["required"]

    # optional_str has a default so it should NOT be required
    assert "optional_str" not in required
    assert "text" in required
    assert "count" in required


def test_schema_description_from_docstring():
    from sophonic.llm import _build_tools

    tools = _build_tools({"sample": sample_fn})
    assert tools[0]["description"] == "Sample tool for schema testing."


def test_build_system_prompt_contains_skill_index(monkeypatch):
    """_build_system_prompt() should include the skill index."""
    from unittest.mock import patch
    from sophonic import skills as _skills
    from sophonic import llm

    fake_skills = [
        _skills.SkillMeta(name="gcal", description="Calendar events", tools=[], body=""),
    ]
    with patch.object(_skills, "discover", return_value=fake_skills):
        prompt = llm._build_system_prompt()
    assert "Sophonic" in prompt
    assert "gcal" in prompt
    assert "Calendar events" in prompt


def test_skill_load_in_tools_list(monkeypatch):
    """ask() should include skill_load in the tool definitions sent to Claude."""
    from unittest.mock import MagicMock, patch
    from sophonic import llm, skills as _skills

    fake_skills = [
        _skills.SkillMeta(name="gcal", description="desc", tools=[], body=""),
    ]

    captured_tools = []

    class FakeResponse:
        stop_reason = "end_turn"
        content = [MagicMock(type="text", text="done")]

    class FakeMessages:
        def create(self, **kwargs):
            captured_tools.extend(kwargs.get("tools", []))
            return FakeResponse()

    class FakeClient:
        messages = FakeMessages()

    with patch.object(_skills, "discover", return_value=fake_skills), \
         patch("sophonic.llm._client", return_value=FakeClient()), \
         patch("sophonic.tools.build_registry", return_value={}):
        llm.ask("hello")

    tool_names = [t["name"] for t in captured_tools]
    assert "skill_load" in tool_names
