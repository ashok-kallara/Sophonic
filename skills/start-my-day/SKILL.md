---
name: start-my-day
description: "Start my day" — build today's daily note and merge in Zoom meeting action items, open Google Tasks, Doc action items, and Gmail/Slack/Drive follow-ups clustered by topic, plus a summary of informational Slack channels. Use when the user says "start my day", "morning brief", "what's on today", or asks to pull everything into today's note.
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
   unfinished tasks and follow-ups into `## Tasks` / `## Follow-up`, its unfinished
   `## Meeting Action Items` / `## Message Follow-ups` subsections into today's
   respective sections, and its `## Notes` subsections into today's `## Notes`. The
   Meeting Action Items/Message Follow-ups half of this matters even though steps 3 and
   5 also widen their own fetch windows to cover gaps: that widened window is always
   relative to *today*, not to "whenever this specific item was first surfaced" — an
   item can fall out of it before ever being checked off (e.g. a meeting from 3 days ago
   whose action items are still open, but today's window only reaches back 1 day since
   the last note) and rollover is the only thing carrying it forward past that point.
   Keep that note's date around — steps 3 and 5 reuse it as the start of the Zoom and
   Gmail/Slack windows, so meetings and messages from any gap (a weekend, a missed day)
   get covered, not just today's.

2. **Schedule (if Google is on).** `gcal.py events-today`. Insert a `## Schedule`
   section *before* `## Tasks` with one `- HH:MM — Title` line per event (`@ location`
   if present), or `- _No events_`. Replace the section on re-run, don't stack it.

3. **Zoom action items.** Cover every meeting since the user's last brief, not just
   today's: `zoom.py action-items --since <step 1's prior-note date> --until <today>`.
   If step 1 found no prior note at all (first-ever run, empty vault), fall back to
   `--days 1` (today only). Override with an explicit `--since/--until/--days` or
   `--owner` if the user asks for something narrower/wider. For each returned group,
   under a `## Meeting Action Items` section (placed before `## Notes`), add a
   `### [<meeting> — <date>](<link>)` subheading and one `- [ ] <item> #zoom` per item —
   unless a subheading with that exact heading text already exists (e.g. rollover from
   step 1 already carried it forward), in which case add only the not-yet-present item
   lines under the existing heading instead of creating a duplicate one. Skip any item
   whose text is already present anywhere in *today's* note — that's what keeps
   same-day re-runs idempotent; it's expected and fine for an item to already sit in a
   prior day's note too, since the point of widening the window is to catch meetings
   that happened before today's note existed.

4. **Google Tasks + Doc action items.** `gtasks.py list`. For each task add
   `- [ ] [<title>](<link>) (Google Tasks: <list>) 📅 <due> #gtask` under `## Tasks`
   (omit the `[…](…)` link wrapper when `link` is null; omit `📅 …` when there's no
   due). Dedupe on the title.

   Also (if Google is on) `gdrive.py doc-action-items --days 7` — these are Google
   Docs' own Smart Canvas action-item chips, which don't create a Google Tasks entry
   unless assigned via a resolved @-mention, so `gtasks.py` can't see them (see
   [[gdrive]]). For each result add `- [ ] <item> — from [<file_name>](<file_link>)
   #docaction` under the same `## Tasks` section. Use `#docaction`, not `#gtask` — these
   aren't real Google Tasks. Dedupe on the item text.

5. **Message follow-ups, clustered by topic or correspondent.** Fetch every source that surfaces
   something awaiting your reply, then write them as one set of topic-grouped tasks
   instead of three flat per-source lists:
   - *Google Drive (if Google is on)*: `gdrive.py mentioned-comments --days 7`.
   - *Gmail (if Google is on)*: cover every day since the user's last brief, not just a
     fixed lookback — `days = (today − step 1's prior-note date).days`, then
     `gmail.py followups --days <that>`.
   - *Slack*: same window — `slack.py followups --days <that>`.
   For Gmail/Slack, if step 1 found no prior note at all (first-ever run, empty vault),
   use `--days 1` (today only) instead. Override any source's window with an explicit
   `--days` if the user asks for something narrower/wider (e.g. "just Gmail from the
   last 3 days" scopes only that fetch).

   **Drop what's already handled** before clustering: skip any item whose identifying
   detail already appears anywhere in the note — a Slack permalink, a Gmail
   `thread_id`, or a Drive `file_link` + the first 40 chars of `content`.

   **Cluster in two passes — never force a heading for a group of one.**
   1. *Topic pass* (unchanged): group items that clearly share a subject — the same
      Slack channel/project name, matching keywords in a Gmail subject or Drive file
      name, the same meeting or initiative mentioned across sources. Judgment call, not
      a fixed rule.
   2. *Correspondent pass*, on whatever's left after the topic pass: group remaining
      items by the same person across `<from>`/`<author>` — matching display name,
      regardless of source — even if their subjects are unrelated. This is what catches
      "3 unrelated things are all waiting on the same person" that topic-only
      clustering misses.
   Anything still alone after both passes is **not** given its own heading — collect
   every such leftover item into one shared `### Also flagged` bucket at the end of the
   section instead.

   **Write the result under `## Message Follow-ups`** (placed before `## Notes`): one
   `### <Topic>` or `### <Person>` subheading per real (2+ item) cluster, in the order
   found, followed by `### Also flagged` last for the leftovers — each with checkbox
   items beneath it, keeping their per-source line format and tag:
   - Drive mention: `- [ ] Reply to comment in [<file_name>](<file_link>) by <author>: "<excerpt>" #gdrive`
   - Drive assigned: `- [ ] [<file_name>](<file_link>) — assigned comment by <author>: "<excerpt>" #gdrive`
   - Gmail: `- [ ] Reply to <from> re "<subject>": <snippet> [Open](<link>) #gmail`
   - Slack mention: `- [ ] Reply in <channel> to <from>: <text> <permalink> #slack`
   - Slack dm: `- [ ] Reply to <channel>: <text> <permalink> #slack`
   - Slack later: `- [ ] Follow up (<channel>): <text> <permalink> #slack`
   Truncate Drive `content` to ~60 chars for the excerpt. This section is **appended to,
   not replaced**: if a subheading with the exact same heading text (including
   `### Also flagged`) already exists in `## Message Follow-ups`, add new items under it
   instead of creating a duplicate heading — this keeps already-checked-off items intact
   across re-runs. Don't retroactively re-cluster items already written in a prior
   run — the existing dedupe-before-clustering step already keeps them from being
   touched again.

6. **Slack informational digest.** `slack.py digest` → take the `informational`
   channels and **write a concise summary yourself** (one markdown bullet per channel:
   what's being discussed and whether it needs attention, channel name bold). Put it in
   a `## Slack` section that you **replace** in place each run. Do not shell out to any
   LLM for this — that's your job now.

7. **Report.** Summarize what changed: counts added per source (Zoom / Google Tasks /
   Drive / Gmail / Slack), how many topic groups were created vs. added to, how many
   tasks rolled over, and any sources that need auth or errored (with the fix command).

## Scope flags

Honor the user's intent: "just Zoom", "skip Slack", "action items from the last 3 days"
→ run only the relevant fetches / pass `--days 3` to whichever source(s) that scopes.
Default window for Zoom (step 3) and the Gmail/Slack halves of step 5 is since the last
daily note through today; Drive (step 5) and Doc action items (step 4) default to a
fixed 7 days. An explicit day count overrides that, per source.
