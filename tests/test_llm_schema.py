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
    from akashic.llm import _build_tools

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
    from akashic.llm import _build_tools

    tools = _build_tools({"sample": sample_fn})
    schema = tools[0]["input_schema"]
    required = schema["required"]

    # optional_str has a default so it should NOT be required
    assert "optional_str" not in required
    assert "text" in required
    assert "count" in required


def test_schema_description_from_docstring():
    from akashic.llm import _build_tools

    tools = _build_tools({"sample": sample_fn})
    assert tools[0]["description"] == "Sample tool for schema testing."
