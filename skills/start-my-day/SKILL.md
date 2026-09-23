---
name: start-my-day
description: "Start my day" — build today's daily note and merge in Zoom meeting action items, open Google Tasks, Google Drive open comments, Gmail follow-ups, and Slack follow-ups, plus a summary of informational Slack channels. Use when the user says "start my day", "morning brief", "what's on today", or asks to pull everything into today's note.
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
   template if missing). Find the most recent prior daily note (per [[obsidian]]'s
   rollover rule: glob `<daily_dir>/<daily_prefix>*.md`, parse the ISO date from each
   name, pick the latest one strictly before today) and do an idempotent rollover of its
   unfinished tasks and follow-ups into `## Tasks` / `## Follow-up`, and its `## Notes`
   subsections into today's `## Notes`. Keep that note's date around — steps 3, 6, and 7
   reuse it as the start of the Zoom, Gmail, and Slack windows, so meetings and messages
   from any gap (a weekend, a missed day) get covered, not just today's.

2. **Schedule (if Google is on).** `gcal.py events-today`. Insert a `## Schedule`
   section *before* `## Tasks` with one `- HH:MM — Title` line per event (`@ location`
   if present), or `- _No events_`. Replace the section on re-run, don't stack it.

3. **Zoom action items.** Cover every meeting since the user's last brief, not just
   today's: `zoom.py action-items --since <step 1's prior-note date> --until <today>`.
   If step 1 found no prior note at all (first-ever run, empty vault), fall back to
   `--days 1` (today only). Override with an explicit `--since/--until/--days` or
   `--owner` if the user asks for something narrower/wider. For each returned group,
   under a `## Meeting Action Items` section (placed before `## Notes`), add a
   `### [<meeting> — <date>](<link>)` subheading and one `- [ ] <item> #zoom` per item.
   Skip any item whose text is already present anywhere in *today's* note — that's what
   keeps same-day re-runs idempotent; it's expected and fine for an item to already sit
   in a prior day's note too, since the point of widening the window is to catch
   meetings that happened before today's note existed.

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

6. **Gmail follow-ups (if Google is on).** Cover every day since the user's last brief,
   not just a fixed lookback: `days = (today − step 1's prior-note date).days`, then
   `gmail.py followups --days <that>`. If step 1 found no prior note at all (first-ever
   run, empty vault), fall back to `--days 1` (today only). Override with an explicit
   `--days` if the user asks for something narrower/wider. For each returned item add a
   reply task under `## Tasks` tagged `#gmail`:
   `- [ ] Reply to <from> re "<subject>": <snippet> [Open](<link>) #gmail`
   Skip items whose `thread_id` already appears in the note.

7. **Slack.** Cover every day since the user's last brief, not just a fixed lookback:
   `days = (today − step 1's prior-note date).days`, then
   `slack.py followups --days <that>`. If step 1 found no prior note at all (first-ever
   run, empty vault), fall back to `--days 1` (today only). Override with an explicit
   `--days` if the user asks for something narrower/wider. For each returned item add a
   reply task under `## Tasks` tagged `#slack`, phrased by kind, with the permalink
   appended:
   - `mention`: `Reply in <channel> to <from>: <text> <permalink>`
   - `dm`: `Reply to <channel>: <text> <permalink>`
   - `later`: `Follow up (<channel>): <text> <permalink>`
   Skip items whose permalink already appears in the note.
   Then `slack.py digest` → take the `informational` channels and **write a concise
   summary yourself** (one markdown bullet per channel: what's being discussed and
   whether it needs attention, channel name bold). Put it in a `## Slack` section that
   you **replace** in place each run. Do not shell out to any LLM for this — that's your
   job now.

8. **Report.** Summarize what changed: counts added per source (Zoom / Google Tasks /
   Drive / Gmail / Slack), how many tasks rolled over, and any sources that need auth or
   errored (with the fix command).

## Scope flags

Honor the user's intent: "just Zoom", "skip Slack", "action items from the last 3 days"
→ run only the relevant steps / pass `--days 3` to whichever source(s) that scopes.
Default window for Zoom (step 3), Gmail follow-ups (step 6), and Slack follow-ups
(step 7) is since the last daily note through today — an explicit day count overrides
that, per source.
