"""GitLab integration — MCP proxy to a self-hosted GitLab instance."""

from __future__ import annotations

import uuid
import warnings
from typing import Any, Callable

import httpx

from sophonic.config import GitLabConfig


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def build_tools(cfg: GitLabConfig) -> dict[str, Callable[..., Any]]:
    """Discover tools from the GitLab MCP endpoint and return {gitlab_*: fn}.

    Returns {} with a warning if the endpoint is unreachable or config is incomplete.
    """
    if not cfg.url or not cfg.token:
        warnings.warn(
            "GitLab integration enabled but url or token not configured — gitlab tools disabled.",
            stacklevel=2,
        )
        return {}

    mcp_url = cfg.url.rstrip("/") + "/api/v4/mcp"

    try:
        tool_descriptors = _discover(mcp_url, cfg.token)
    except Exception as exc:
        warnings.warn(
            f"GitLab MCP endpoint unreachable ({exc}) — gitlab tools disabled.",
            stacklevel=2,
        )
        return {}

    return {
        f"gitlab_{t['name']}": _make_caller(
            t["name"], mcp_url, cfg.token, t.get("description", t["name"])
        )
        for t in tool_descriptors
    }


def _discover(mcp_url: str, token: str) -> list[dict[str, Any]]:
    """POST tools/list and return the tool descriptor list."""
    resp = httpx.post(
        mcp_url,
        json={"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/list", "params": {}},
        headers=_auth_headers(token),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"GitLab MCP error: {data['error']}")
    result = data.get("result")
    if result is None or "tools" not in result:
        raise RuntimeError(f"Unexpected MCP response shape: {data!r}")
    return result["tools"]


def _make_caller(
    native_name: str, mcp_url: str, token: str, description: str
) -> Callable[..., Any]:
    """Return a sync wrapper that POSTs tools/call for native_name."""

    def wrapper(**kwargs: Any) -> Any:
        resp = httpx.post(
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {"name": native_name, "arguments": kwargs},
            },
            headers=_auth_headers(token),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"GitLab MCP error: {data['error']}")
        return data["result"]

    wrapper.__doc__ = description
    wrapper.__name__ = f"gitlab_{native_name}"
    return wrapper
