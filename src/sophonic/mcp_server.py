"""Single sophonic-mcp server — FastMCP, namespaced tools gated by feature flags."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sophonic.tools import build_registry


def main() -> None:
    mcp = FastMCP(
        "sophonic",
        instructions=(
            "Obsidian-native AI assistant. Reads/writes Obsidian tasks and notes, "
            "queries Google Calendar and Gmail, scrapes Slack unread messages, "
            "and fetches Zoom meeting transcripts."
        ),
    )

    registry = build_registry()
    for name, fn in registry.items():
        mcp.add_tool(fn, name=name, description=(fn.__doc__ or name).strip())

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
