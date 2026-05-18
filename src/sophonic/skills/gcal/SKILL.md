---
name: gcal
description: Read Google Calendar events. Trigger when the user asks about their schedule, upcoming meetings, or availability.
tools:
  - gcal_events_today
  - gcal_events_range
---

# Google Calendar

Read-only access to the user's primary Google Calendar.

## Tools

- `gcal_events_today()` — Return today's events as `{title, start, end, location, description, link}`.
- `gcal_events_range(start_date, end_date)` — Return events between two ISO dates (inclusive).

## When to use

Always call a gcal tool before answering questions about the user's schedule, meetings, or availability. Never infer times from memory.

## Auth

If a Google auth error is returned, tell the user to run `sophonic auth google`.
