---
name: start-my-day
description: "Start my day" — build today's daily note and merge in Zoom meeting action items, open Google Tasks, Google Drive open comments, and Slack follow-ups, plus a summary of informational Slack channels. Use when the user says "start my day", "morning brief", "what's on today", or asks to pull everything into today's note.
---

# Start my day

Assemble today's brief in the daily note. You edit the vault yourself (see [[obsidian]])
and call the thin fetch-scripts only for the auth-bound sources. Each source is
independent: if one is unauthenticated or fails, report it and keep going — never abort
the whole brief. Everything you write must be **deduped against the current note** so
re-running is safe.

## Script invocation

All fetchers print a single JSON object; run them with the Bash tool:

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py" <action> [flags]
```

If any result contains `{"needs_auth": true, "run": "..."}` or `{"error": "..."}`,
surface that source's status (and the `run` command for the user's terminal) and move on.

## Procedure

1. **Daily note + rollover.** Ensure today's note exists (create from the [[obsidian]]
   template if missing). Do an idempotent rollover of the most recent prior note's
   unfinished tasks into `## Tasks`.

2. **Schedule (if Google is on).** `gcal.py events-today`. Insert a `## Schedule`
   section *before* `## Tasks` with one `- HH:MM — Title` line per event (`@ location`
   if present), or `- _No events_`. Replace the section on re-run, don't stack it.

3. **Zoom action items.** `zoom.py action-items --days 1` (today's meetings; widen with
   `--since/--until/--days` or `--owner` if the user asks). For each returned group,
   under a `## Meeting Action Items` section (placed before `## Notes`), add a
   `### [<meeting> — <date>](<link>)` subheading and one `- [ ] <item> #zoom` per item.
   Skip any item whose text is already present anywhere in the note.

4. **Google Tasks.** `gtasks.py list`. For each task add
   `- [ ] [<title>](<link>) (Google Tasks: <list>) 📅 <due> #gtask` under `## Tasks`
   (omit the `[…](…)` link wrapper when `link` is null; omit `📅 …` when there's no
   due). Dedupe on the title.

5. **Google Drive comments (if Google is on).** `gdrive.py mentioned-comments --days 7`.
   For each result add a task under `## Tasks` tagged `#gdrive`:
   - mention: `- [ ] Reply to comment in [<file_name>](<file_link>) by <author>: "<excerpt>" #gdrive`
   - assigned: `- [ ] [<file_name>](<file_link>) — assigned comment by <author>: "<excerpt>" #gdrive`
   Truncate `content` to ~60 chars for the excerpt. Skip items where the `file_link`
   and the first 40 chars of `content` already appear together in the note.

6. **Slack.** `slack.py followups` → for each item add a reply task under `## Tasks`
   tagged `#slack`, phrased by kind, with the permalink appended:
   - `mention`: `Reply in <channel> to <from>: <text> <permalink>`
   - `dm`: `Reply to <channel>: <text> <permalink>`
   - `later`: `Follow up (<channel>): <text> <permalink>`
   Skip items whose permalink already appears in the note.
   Then `slack.py digest` → take the `informational` channels and **write a concise
   summary yourself** (one markdown bullet per channel: what's being discussed and
   whether it needs attention, channel name bold). Put it in a `## Slack` section that
   you **replace** in place each run. Do not shell out to any LLM for this — that's your
   job now.

7. **Report.** Summarize what changed: counts added per source (Zoom / Google Tasks /
   Drive / Slack), how many tasks rolled over, and any sources that need auth or errored
   (with the fix command).

## Scope flags

Honor the user's intent: "just Zoom", "skip Slack", "action items from the last 3 days"
→ run only the relevant steps / pass `--days 3`. Default window for Zoom is today.
