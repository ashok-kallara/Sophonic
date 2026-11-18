---
name: zoom
description: Read Zoom AI Companion meeting notes (read-only) — list notes, fetch a note's content, or extract action items over a date window. Uses the Zoom MCP (e.g. via Runlayer) by default and falls back to a cookie-based script when no Zoom MCP is available. Use when the user asks about Zoom meeting notes, recaps, or action items from meetings.
---

# Zoom AI meeting notes

Zoom auto-generates an AI Companion "Note" per meeting. This skill reads them **read-only**;
you write anything that lands in the vault (see [[obsidian]]).

There are two sources. **Always try the MCP first.**

1. **Zoom MCP (default)** — you call Zoom's own tools. No cookies, no browser, nothing to
   expire in the terminal.
2. **Cookie script (fallback)** — `scripts/zoom.py`, only when no Zoom MCP is reachable.

Other skills ([[meeting-recap]], [[start-my-day]], [[ask]]) defer to this one for *how* to
fetch; they only describe what to do with the result.

## 1. Zoom MCP (default)

### Finding the tools

Look for `zoom_search` and `my_notes_get_note_content` in your tool list (they may carry an
MCP prefix). If the Runlayer plugin is connected and doesn't list them directly, use its
`search_tools` ("zoom my notes search") and call them through `execute_tool` with the exact
returned name. Follow Runlayer's rule for placeholders: if what you find is a
`DISABLED_` / `AUTH_REQUIRED_` / `INPUTS_REQUIRED_` tool, call it directly and relay its
instructions to the user — then see *When to fall back* below.

### List notes — `zoom_search`

```json
{
  "datasource_filters": [{
    "datasource": "zoom_my_notes",
    "filters": {"and": [
      {"gte": {"key": "create_time", "value": "<window start, UTC ISO 8601>"}},
      {"lte": {"key": "create_time", "value": "<window end, UTC ISO 8601>"}}
    ]}
  }],
  "page_size": 50
}
```

- Omit `query` — the date window is a filter, not a search term. `query` is for finding notes
  by **title keyword** ("Databricks" returned only notes with it in the title): `title` is the
  only searchable field on `zoom_my_notes`, so it does **not** search note bodies. To answer a
  question about what was *said*, list by date window (or by title keyword), then fetch and read
  the likely notes. You may drop the date filter when searching by title.
- **Time zone.** `create_time` is UTC. Build the window from the user's *local* day
  boundaries (`date +%z` gives the offset) converted to UTC — an evening meeting is already
  "tomorrow" in UTC, so a naive UTC day drops or misfiles it. Display dates in local time.
- Each result: `{file_id, title, link, create_time, modify_time, created_by}`. Results are
  newest-first. When `has_more` is true, pass `next_page_token` with the *same* request to
  continue; default `page_size` is 10, max 100.
- Only the `zoom_my_notes` datasource and the `create_time` field are verified. Before using
  any other filter field, call `search_describe_capabilities` (`tool=search`).

### Fetch one note — `my_notes_get_note_content`

```json
{"noteId": "<file_id>"}
```

**Never pass `"include": "transcript"`.** Sophonic works from the AI summary only: a
transcript is ~35x the size of its summary (a 30-minute meeting was ~73 KB of JSON,
~18k tokens) and adds nothing the summary's takeaways and action items don't already
cover. If the user explicitly asks to read a transcript, tell them it is costly and
confirm first.

Returns `{note_id, note_name, note_url, generated_note_content, manual_note_content}`:

- `generated_note_content` — the **AI Companion summary**, clean markdown with `##` headings
  (Key Outcomes, Decisions Made, Blockers Requiring Action, Pending Confirmation,
  **Action Items**, …; the exact set varies by meeting). This is the field every Sophonic
  skill uses. It has none of the scrape artifacts the cookie path has (no UI footer, no
  table-of-contents block, and no zero-width characters or split bullets in the notes checked).
- `manual_note_content` — what the user typed themselves. **Ignore it** for recaps and action
  items: it is hand-authored, not meeting output.
- Both empty → the AI summary isn't ready (or the meeting had no AI Companion). Treat as
  "no content yet", not an error.

### Identity and links

- Dedupe on the **`file_id`** (the Zoom doc id) — match it as a substring, so entries written
  earlier by the cookie path (different URL host) still count as already present.
- When you write a link, use `https://docs.zoom.us/doc/<file_id>` — the same form the
  fallback script uses, so old and new entries look alike.

### Action items from the MCP

Take the bullets under the `## Action Items` heading of `generated_note_content` (also
`Next Steps` / `Follow-ups` / `To-dos` if present instead). Per item:

- Strip markdown emphasis (`**Sope:** Review…` → `Sope: Review…`), so the text matches what
  the fallback script produced and dedupes against earlier days' tasks.
- Collapse to a single line.
- `--owner`-style filtering: keep only items whose text contains the name (case-insensitive).

Group by meeting: `{meeting: note_name, date: <local date of create_time>, link, items,
summary_ready}`.

The summary is the **only** source — never derive action items from a transcript.

- **Summary empty** → the AI summary isn't generated yet (a note was empty right after its
  meeting and filled in minutes later). Don't drop the meeting: return it as a group with
  `items: []` and `summary_ready: false`, so the caller can show it as "summary not ready"
  ([[start-my-day]] writes that into the daily note). It is picked up on a later run once
  Zoom finishes the summary. Every other group has `summary_ready: true`.
- **Summary present but no action-item section** → the meeting simply had none. Report the
  meeting as "no action items"; don't go looking elsewhere for them.

## 2. Cookie script (fallback)

Reads the signed-in Zoom web session (pasted `ZOOM_COOKIES`) in headless Chromium. Slower
(~6 s per note) and the session expires, which is exactly why the MCP is the default.

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" check-auth
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" notes --limit 20
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" note --id <doc_id>
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" action-items --days 1 --owner "Jane"
```

- `notes` — recent notes `{id, title, meeting, date, link, is_meeting_note}`.
- `note` — one note's `{id, title, text}`; `text` is a scraped blob (see [[meeting-recap]]
  for how it is trimmed).
- `action-items` — items grouped by meeting: `{range, meetings_scanned, count,
  groups:[{meeting, date, link, items:[…]}]}`. Only bulleted lines under an
  "Action Items" / "Next Steps" / "Follow-ups" heading become items. Window defaults to
  today; widen with `--on/--since/--until/--days`; `--owner` keeps only items containing
  that substring.

Auth: if a result has `{"needs_auth": true}` (or `check-auth` reports the session expired),
tell the user to run in their terminal `sophonic-config set-secret ZOOM_COOKIES --stdin` and
paste the `Cookie:` request-header value from https://zoom.us (DevTools → Network). Setup:
[[setup]].

## When to fall back

Use the cookie script **only** if the MCP path is unavailable:

- no `zoom_search` / `my_notes_get_note_content` tool exists anywhere (no Zoom MCP
  installed or connected), or
- the MCP tool is an auth/disabled placeholder the user can't resolve right now.

Do **not** fall back for an ordinary empty result — "no notes in that window" is a normal
answer. And don't silently switch mid-run: if you fall back, say so ("Zoom MCP isn't
connected — using the cookie fallback"), and if *both* fail report both reasons so the user
can fix whichever is easier.

## Writing to the vault (you do this)

- **Action items → tasks:** for each group, add a `### [<meeting> — <date>](<link>)`
  subheading under `## Meeting Action Items` with `- [ ] <item> #zoom`, deduped against
  the note (see [[obsidian]]). This is exactly what [[start-my-day]] does.
- **Save a note as a meeting note:** fetch it, then file it per the [[obsidian]]
  meeting-note contract (frontmatter `source: zoom`, the note content, and a backlink in
  today's daily note).
