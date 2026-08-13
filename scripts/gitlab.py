#!/usr/bin/env python3
"""GitLab via the instance's own MCP endpoint (/api/v4/mcp) → JSON.

    uv run python scripts/gitlab.py tools
    uv run python scripts/gitlab.py call --tool gitlab_get_issue --args-json '{"id":"123"}'

`tools` lists the gitlab_* tools the instance exposes (name + description).
`call` invokes one and prints its result. Requires [gitlab] url + token in config
(or the GITLAB_TOKEN secret). Needs GitLab 17.3+ which ships the MCP endpoint.
"""

from __future__ import annotations

import argparse
import json

from _common import emit, run


def _tools() -> dict:
    from sophonic.config import load_config
    from sophonic.gitlab import build_tools

    reg = build_tools(load_config().gitlab)
    return {
        "tools": [
            {"name": name, "description": (fn.__doc__ or name).strip().split("\n")[0]}
            for name, fn in sorted(reg.items())
        ]
    }


def _call(tool: str, args_json: str) -> dict:
    from sophonic.config import load_config
    from sophonic.gitlab import build_tools

    reg = build_tools(load_config().gitlab)
    fn = reg.get(tool)
    if fn is None:
        return {"error": f"Unknown GitLab tool: {tool}", "available": sorted(reg)}
    kwargs = json.loads(args_json)
    if not isinstance(kwargs, dict):
        return {"error": "--args-json must be a JSON object of keyword arguments"}
    return fn(**kwargs)


def main() -> None:
    p = argparse.ArgumentParser(description="GitLab MCP proxy.")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("tools", help="List available gitlab_* tools")
    c = sub.add_parser("call", help="Invoke one gitlab_* tool")
    c.add_argument("--tool", required=True, help="e.g. gitlab_get_issue")
    c.add_argument("--args-json", default="{}", help="JSON object of keyword arguments")
    args = p.parse_args()

    if args.action == "tools":
        run(_tools)
    else:
        run(_call, args.tool, args.args_json)


if __name__ == "__main__":
    main()
