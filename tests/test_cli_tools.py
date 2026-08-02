"""Tests for the generic `sophonic tools` / `sophonic tool` dispatch commands.

These power the MCP-free Claude Code plugin: they expose the same feature-gated
registry the MCP server uses, with machine-readable JSON output.
"""

import json
from unittest.mock import patch

from typer.testing import CliRunner

from sophonic.cli import app

runner = CliRunner()


def _echo(text: str, times: int = 1) -> dict:
    """Echo the given text."""
    return {"echoed": text * times}


def test_tools_lists_registry_names_as_json():
    with patch("sophonic.tools.build_registry", return_value={"echo": _echo}):
        result = runner.invoke(app, ["tools"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    names = {entry["name"] for entry in payload}
    assert "echo" in names
    assert "skill_load" in names  # merged in, mirroring the MCP server
    echo_entry = next(e for e in payload if e["name"] == "echo")
    assert echo_entry["description"] == "Echo the given text."


def test_tool_invokes_and_prints_json_result():
    with patch("sophonic.tools.build_registry", return_value={"echo": _echo}):
        result = runner.invoke(app, ["tool", "echo", "--args-json", '{"text": "hi", "times": 3}'])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"echoed": "hihihi"}


def test_tool_defaults_to_empty_args():
    def ping() -> dict:
        """Ping."""
        return {"pong": True}

    with patch("sophonic.tools.build_registry", return_value={"ping": ping}):
        result = runner.invoke(app, ["tool", "ping"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"pong": True}


def test_tool_unknown_name_errors_with_nonzero_exit():
    with patch("sophonic.tools.build_registry", return_value={"echo": _echo}):
        result = runner.invoke(app, ["tool", "does_not_exist"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert "error" in payload
    assert "does_not_exist" in payload["error"]
    assert "echo" in payload["available"]


def test_tool_bad_json_errors_with_nonzero_exit():
    with patch("sophonic.tools.build_registry", return_value={"echo": _echo}):
        result = runner.invoke(app, ["tool", "echo", "--args-json", "not-json"])

    assert result.exit_code == 1
    assert "error" in json.loads(result.stdout)


def test_tool_non_object_json_errors():
    with patch("sophonic.tools.build_registry", return_value={"echo": _echo}):
        result = runner.invoke(app, ["tool", "echo", "--args-json", "[1, 2, 3]"])

    assert result.exit_code == 1
    assert "error" in json.loads(result.stdout)


def test_tool_surfaces_tool_exceptions_as_json():
    def boom() -> dict:
        """Always fails."""
        raise RuntimeError("kaboom")

    with patch("sophonic.tools.build_registry", return_value={"boom": boom}):
        result = runner.invoke(app, ["tool", "boom"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == "kaboom"
