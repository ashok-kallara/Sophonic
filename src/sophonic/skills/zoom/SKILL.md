---
name: zoom
description: List and save Zoom's AI-generated meeting notes (AI Companion). Trigger when the user asks about a recent meeting, its notes, action items, or summary.
tools:
  - zoom_check_auth
  - zoom_notes
  - zoom_note
  - zoom_save_note
  - zoom_action_items
---

# Zoom (AI meeting notes)

Reads Zoom's AI Companion meeting notes from the signed-in web session (Zoom Docs).
No cloud recording required — Zoom auto-generates a Note for each meeting.

## Tools

- `zoom_check_auth()` — Lightweight validity probe for the Zoom web session (no browser): `{ok, detail}`. Use to tell "cookies expired" from "cookies missing".
- `zoom_notes(limit)` — List recent AI meeting notes: `{id, title, meeting, date, link, is_meeting_note}`.
- `zoom_note(doc_id)` — Return the note's content (Key Outcomes, Decisions, Action Items, …).
- `zoom_save_note(doc_id, title)` — Fetch a note and save it as an Obsidian meeting note (backlinked in the daily note).
- `zoom_action_items(on, since, until, days, owner, dry_run)` — Extract action items from meeting notes in a date window and write them to today's note under a dedicated `## Meeting Action Items` section, **grouped by meeting** (a `### [Meeting — date](link)` subheading per meeting, with `- [ ] … #zoom` checkboxes). Only bulleted entries under an "Action Items"/"Next Steps"/"Follow-ups" heading become tasks — narrative/summary prose is ignored. Defaults to today's meetings; use `days` (last N days) or `on`/`since`/`until` (ISO or natural language) to widen it. `owner` keeps only items containing that substring; `dry_run` previews. Append-only and deduped (preserves checked items), so it's safe to re-run. Returns `groups` (per meeting) and a total `count`.

## Auth

If `{"needs_auth": true}` is returned, the Zoom web session cookies are missing/expired.
Tell the user to log in to zoom.us, then in browser DevTools → Network copy the whole
`Cookie:` request-header value from any zoom.us request and run
`sophonic config set-secret ZOOM_COOKIES --stdin` (paste on one line, then press Return). The value is the
`name=value; name2=value2` string; a leading `Cookie:` label is accepted and stripped.

## When to use

Use when the user asks about a recent meeting, its summary, decisions, or action items.
Call `zoom_notes` to find the meeting, then `zoom_save_note` (or `zoom_note`) for its content.

When the user wants a meeting's action items added to their task list, call `zoom_action_items`.
"today"/no date → default (today's meetings); "yesterday" → `on="yesterday"`; "last 3 days" → `days=3`;
an explicit span → `since`/`until`. Report what was added; suggest `dry_run=True` first if they want a preview.
