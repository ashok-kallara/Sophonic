---
name: zoom
description: Read Zoom AI Companion meeting notes from the signed-in web session (read-only) — list notes, fetch a note's content, or extract action items over a date window. Use when the user asks about Zoom meeting notes, recaps, or action items from meetings.
---

# Zoom AI meeting notes

Zoom auto-generates an AI Companion "Note" per meeting (stored in Zoom Docs). This reads
them from your authenticated web session (seeded from pasted cookies) via a thin
fetch-script. The script only **reads** — you write anything that lands in the vault
(see [[obsidian]]).

## Run

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" check-auth
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" notes --limit 20
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" note --id <doc_id>
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" action-items --days 1 --owner "Jane"
```

- `notes` — recent notes `{id, title, meeting, date, link, is_meeting_note}`.
- `note` — one note's `{id, title, text}`.
- `action-items` — items grouped by meeting: `{range, meetings_scanned, count,
  groups:[{meeting, date, link, items:[…]}]}`. Only bulleted lines under an
  "Action Items" / "Next Steps" / "Follow-ups" heading become items. Window defaults to
  today; widen with `--on/--since/--until/--days`; `--owner` keeps only items containing
  that substring.

## Writing to the vault (you do this)

- **Action items → tasks:** for each group, add a `### [<meeting> — <date>](<link>)`
  subheading under `## Meeting Action Items` with `- [ ] <item> #zoom`, deduped against
  the note (see [[obsidian]]). This is exactly what [[start-my-day]] does.
- **Save a note as a meeting note:** fetch it with `note --id`, then file it per the
  [[obsidian]] meeting-note contract (frontmatter `source: zoom`, the note `text`, and a
  backlink in today's daily note).

## Auth

Uses a pasted web session. If a result has `{"needs_auth": true}` (or `check-auth`
reports the session expired), tell the user to run in their terminal:
`uv run python scripts/config.py set-secret ZOOM_COOKIES --stdin` and paste the
`Cookie:` request-header value from https://zoom.us (DevTools → Network). Setup:
[[setup]].
