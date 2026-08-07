---
name: daybrief
description: Build the user's daily brief — merge Zoom meeting action items, open Google Tasks, and Slack into today's note. Trigger on "start my day", "what's on my plate", "pull everything into today".
tools:
  - day_start
---

# Daily brief (start my day)

`day_start` composes the whole day in one call and is safe to re-run (everything dedupes).

## Tool

- `day_start(on, since, until, days, owner, dry_run, skip_zoom, skip_tasks, skip_slack)`:
  1. Ensures today's daily note (calendar schedule + rolled-over incompletes).
  2. Writes Zoom meeting action items to a `## Meeting Action Items` section grouped by meeting (window: `on`/`since`/`until`/`days`, default today; `owner` filters). Only bulleted Action Items/Next Steps become tasks.
  3. Merges open Google Tasks into `## Tasks` (with due dates).
  4. Turns Slack DMs/@-mentions into `Reply to …` tasks; summarizes other unread channels into a refreshable `## Slack` section.
  Returns per-source counts and a `sources` status list (each `{name, ok, detail}`); a disabled/unauth/failing source is skipped, never fatal.

## When to use

Use for "start my day", "refresh today", or "pull my meetings/tasks/Slack into today".
Report the per-source counts and surface any source whose `ok` is false (with its `run` fix, if present).
For a Zoom-only pull, use `zoom_action_items` instead; for just the note, `obsidian_build_daily_note`.
