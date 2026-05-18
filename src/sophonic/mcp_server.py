"""Single sophonic-mcp server — FastMCP, namespaced tools gated by feature flags."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sophonic import skills as _skills
from sophonic.tools import build_registry


def main() -> None:
    all_skills = _skills.discover()
    idx = _skills.index()

    instructions = (
        "Obsidian-native AI assistant. Reads/writes Obsidian tasks and notes, "
        "queries Google Calendar and Gmail, scrapes Slack unread messages, "
        "and fetches Zoom meeting transcripts.\n\n" + idx
        if idx
        else "Obsidian-native AI assistant."
    )

    mcp = FastMCP("sophonic", instructions=instructions)

    registry = build_registry()
    for name, fn in registry.items():
        mcp.add_tool(fn, name=name, description=(fn.__doc__ or name).strip())

    mcp.add_tool(
        _skills.skill_load,
        name="skill_load",
        description="Load the full instructions for a named capability. Call this before using an unfamiliar set of tools.",
    )

    for skill_meta in all_skills:
        def _make_prompt_fn(body: str):
            def prompt_fn() -> str:
                return body
            return prompt_fn
        mcp.prompt(name=skill_meta.name, description=skill_meta.description)(
            _make_prompt_fn(skill_meta.body)
        )

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
