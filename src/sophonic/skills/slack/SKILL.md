---
name: slack
description: Read Slack unread messages and search history via browser scraper. Trigger when the user asks about Slack messages or channels.
tools:
  - slack_unread
  - slack_search
---

# Slack

Browser-scraper access to Slack (used when the Slack MCP server is unavailable due to admin restrictions).

## Tools

- `slack_unread(limit)` — Return unread messages across all channels as `{channel, sender, text, ts}`.
- `slack_search(query, limit)` — Search Slack history. Returns `{channel, sender, text, ts, permalink}`.

## Auth

If `{"needs_auth": true}` is returned, tell the user to run `sophonic auth slack` to log in via the browser.

## When to use

Use when the user asks "what did I miss on Slack" or mentions a specific Slack message or channel. Prefer the Slack MCP server if available; use these as fallback.
