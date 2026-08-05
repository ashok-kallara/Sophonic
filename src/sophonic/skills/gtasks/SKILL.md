---
name: gtasks
description: Read the user's open Google Tasks across all task lists. Trigger when the user asks about their to-dos, Google Tasks, or wants those merged into today's list.
tools:
  - gtasks_list
---

# Google Tasks (read-only)

Reads open (incomplete) tasks from the user's Google Tasks lists.

## Tools

- `gtasks_list(max_lists, max_tasks)` — Open tasks across all lists: `{id, title, notes, due, list, list_id}`.

## Auth

Google Tasks needs the `tasks.readonly` OAuth scope. If the tool returns `{"needs_auth": true}`,
the signed-in token predates that scope — tell the user to run the `run` command it returns
(sets the scope in config and re-runs `sophonic auth google`).

## When to use

Use when the user asks about their Google to-dos, or wants them pulled into today's tasks.
The `day_start` tool already merges open Google Tasks into the daily note.
