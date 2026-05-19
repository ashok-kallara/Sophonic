"""Tests for the GitLab MCP proxy."""

from __future__ import annotations

import warnings
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _cfg(url: str = "https://gitlab.example.com", token: str = "glpat-abc", default_project: str = ""):
    from sophonic.config import GitLabConfig
    return GitLabConfig(url=url, token=token, default_project=default_project)


def _tools_list_response(tools: list[dict[str, Any]]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": "1",
        "result": {"tools": tools},
    }
    resp.raise_for_status = MagicMock()
    return resp


def _tool_call_response(result: Any) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": "2",
        "result": result,
    }
    resp.raise_for_status = MagicMock()
    return resp


# ── build_tools — discovery ───────────────────────────────────────────────────

@patch("sophonic.tools.gitlab.httpx.post")
def test_build_tools_discovers_tools_and_prefixes_names(mock_post):
    from sophonic.tools.gitlab import build_tools

    mock_post.return_value = _tools_list_response([
        {"name": "list_issues", "description": "List issues"},
        {"name": "create_issue", "description": "Create an issue"},
    ])

    tools = build_tools(_cfg())

    assert "gitlab_list_issues" in tools
    assert "gitlab_create_issue" in tools
    assert len(tools) == 2


@patch("sophonic.tools.gitlab.httpx.post")
def test_build_tools_sets_doc_from_description(mock_post):
    from sophonic.tools.gitlab import build_tools

    mock_post.return_value = _tools_list_response([
        {"name": "list_issues", "description": "List project issues"},
    ])

    tools = build_tools(_cfg())

    assert tools["gitlab_list_issues"].__doc__ == "List project issues"


@patch("sophonic.tools.gitlab.httpx.post")
def test_build_tools_discovery_uses_bearer_auth(mock_post):
    from sophonic.tools.gitlab import build_tools

    mock_post.return_value = _tools_list_response([])
    build_tools(_cfg(token="glpat-mytoken"))

    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer glpat-mytoken"


@patch("sophonic.tools.gitlab.httpx.post")
def test_build_tools_discovery_posts_to_mcp_endpoint(mock_post):
    from sophonic.tools.gitlab import build_tools

    mock_post.return_value = _tools_list_response([])
    build_tools(_cfg(url="https://gitlab.example.com/"))

    args, kwargs = mock_post.call_args
    assert args[0] == "https://gitlab.example.com/api/v4/mcp"
    assert kwargs["json"]["method"] == "tools/list"


# ── build_tools — tool call wrapper ──────────────────────────────────────────

@patch("sophonic.tools.gitlab.httpx.post")
def test_tool_wrapper_passes_kwargs_as_arguments(mock_post):
    from sophonic.tools.gitlab import build_tools

    mock_post.side_effect = [
        _tools_list_response([{"name": "list_issues", "description": "List issues"}]),
        _tool_call_response([{"iid": 1, "title": "Bug"}]),
    ]

    tools = build_tools(_cfg())
    result = tools["gitlab_list_issues"](project="group/repo", state="opened")

    tool_call = mock_post.call_args_list[1]
    _, kwargs = tool_call
    params = kwargs["json"]["params"]
    assert params["name"] == "list_issues"
    assert params["arguments"] == {"project": "group/repo", "state": "opened"}


@patch("sophonic.tools.gitlab.httpx.post")
def test_tool_wrapper_returns_result_field(mock_post):
    from sophonic.tools.gitlab import build_tools

    expected = [{"iid": 42, "title": "My issue"}]
    mock_post.side_effect = [
        _tools_list_response([{"name": "get_issue", "description": "Get issue"}]),
        _tool_call_response(expected),
    ]

    tools = build_tools(_cfg())
    result = tools["gitlab_get_issue"](project="group/repo", issue_iid=42)

    assert result == expected


@patch("sophonic.tools.gitlab.httpx.post")
def test_tool_wrapper_raises_on_mcp_error(mock_post):
    from sophonic.tools.gitlab import build_tools

    error_resp = MagicMock()
    error_resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": "2",
        "error": {"code": -32600, "message": "Invalid project"},
    }
    error_resp.raise_for_status = MagicMock()

    mock_post.side_effect = [
        _tools_list_response([{"name": "list_issues", "description": "List"}]),
        error_resp,
    ]

    tools = build_tools(_cfg())
    with pytest.raises(RuntimeError, match="Invalid project"):
        tools["gitlab_list_issues"](project="bad/project")


# ── build_tools — graceful degradation ───────────────────────────────────────

@patch("sophonic.tools.gitlab.httpx.post")
def test_build_tools_connect_error_returns_empty_dict(mock_post):
    import httpx
    from sophonic.tools.gitlab import build_tools

    mock_post.side_effect = httpx.ConnectError("Connection refused")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tools = build_tools(_cfg())

    assert tools == {}
    assert any("unreachable" in str(w.message).lower() for w in caught)


@patch("sophonic.tools.gitlab.httpx.post")
def test_build_tools_http_error_returns_empty_dict(mock_post):
    import httpx
    from sophonic.tools.gitlab import build_tools

    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401", request=MagicMock(), response=MagicMock()
    )
    mock_post.return_value = resp

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tools = build_tools(_cfg())

    assert tools == {}
    assert any("unreachable" in str(w.message).lower() for w in caught)


def test_build_tools_empty_url_returns_empty_dict():
    from sophonic.tools.gitlab import build_tools

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tools = build_tools(_cfg(url=""))

    assert tools == {}
    assert any("url" in str(w.message).lower() or "token" in str(w.message).lower() for w in caught)


def test_build_tools_empty_token_returns_empty_dict():
    from sophonic.tools.gitlab import build_tools

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tools = build_tools(_cfg(token=""))

    assert tools == {}
    assert any("url" in str(w.message).lower() or "token" in str(w.message).lower() for w in caught)


# ── build_registry integration ────────────────────────────────────────────────

@patch("sophonic.tools.gitlab.httpx.post")
def test_build_registry_includes_gitlab_tools_when_enabled(mock_post, monkeypatch):
    """build_registry() registers gitlab_* tools when features.gitlab = True."""
    monkeypatch.setenv("SOPHONIC_VAULT", "/tmp/sophonic_test")
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-test")

    from sophonic.config import Config, FeaturesConfig, GitLabConfig, load_config
    load_config.cache_clear()

    mock_post.return_value = _tools_list_response([
        {"name": "list_issues", "description": "List issues"},
    ])

    gitlab_cfg = Config(
        features=FeaturesConfig(gitlab=True, google=False, slack=False, zoom=False),
        gitlab=GitLabConfig(url="https://gitlab.example.com", token="glpat-test"),
    )

    with patch("sophonic.tools.load_config", return_value=gitlab_cfg), \
         patch("sophonic.skills.validate"):
        from sophonic.tools import _REGISTRY, build_registry
        _REGISTRY.clear()
        registry = build_registry()

    assert "gitlab_list_issues" in registry
    load_config.cache_clear()
