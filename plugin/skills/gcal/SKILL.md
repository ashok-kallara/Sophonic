---
description: Read Google Calendar events. Use when the user asks about their schedule, upcoming meetings, or availability.
---

# Google Calendar

Read-only access to the user's primary Google Calendar.

> **How to run these tools:** use the Bash tool —
> `sophonic tool <NAME> --args-json '<JSON kwargs>'`. Prints JSON, no API key.

## Tools

- `gcal_events_today()` — Today's events as `{title, start, end, location, description, link}`.
- `gcal_events_range(start_date, end_date)` — Events between two ISO dates (inclusive).

## Examples

```bash
sophonic tool gcal_events_today
sophonic tool gcal_events_range --args-json '{"start_date":"2026-08-01","end_date":"2026-08-07"}'
```

## When to use

Always call a gcal tool before answering about the user's schedule, meetings, or availability. Never infer times from memory.

## Auth

If a Google auth error is returned, tell the user to run `sophonic auth google`.
