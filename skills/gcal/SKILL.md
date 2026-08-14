---
name: gcal
description: Read the user's Google Calendar (read-only) — today's events or a date range. Use when the user asks about their calendar, schedule, meetings, or availability.
---

# Google Calendar

Read-only access to the primary Google Calendar via a thin fetch-script. Never infer
times from memory — always pull them.

## Run

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gcal.py" events-today
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gcal.py" events-range --start 2026-08-01 --end 2026-08-07
```

Each event: `{title, start, end, location, description, link}`. Timed starts look like
`2026-08-13T09:00:00-04:00`; all-day like `2026-08-13`.

## Auth

Needs Google OAuth. If a call fails with an auth error, tell the user to run in their
terminal: `uv run python scripts/auth.py google` (from the plugin directory). Setup:
[[setup]].
