---
name: gtasks
description: Read the user's open Google Tasks (read-only) across all task lists. Use when the user asks about their Google Tasks or to-do list, or to pull them into the daily note.
---

# Google Tasks

Read-only list of open (incomplete) Google Tasks via a thin fetch-script.

## Run

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gtasks.py" list
```

Returns `[{id, title, notes, due, list, list_id, link, links}]`. `link` is the
`webViewLink` for opening the task in the Google Tasks web UI (may be `null`).
`links` is an array of `{type, description, link}` associated items (e.g. originating
emails).

To land these in the daily note, follow [[obsidian]] — e.g.:
`- [ ] [<title>](<link>) (Google Tasks: <list>) 📅 <due> #gtask`
(omit the `[…](…)` wrapper when `link` is null; omit `📅 …` when there's no due).
The [[start-my-day]] skill already merges these when you "start my day".

## Auth

Needs the `tasks.readonly` scope. If the result is
`{"needs_auth": true, "run": "..."}`, the token lacks that scope — tell the user to run
the returned `run` command in their terminal (it adds the scope and re-consents). Setup:
[[setup]].
