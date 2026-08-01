---
description: List and save Zoom's AI-generated meeting notes (AI Companion). Use when the user asks about a recent meeting, its notes, action items, or summary.
---

# Zoom (AI meeting notes)

Reads Zoom's AI Companion meeting notes from your signed-in Zoom web session (Zoom
Docs). Zoom auto-generates a Note for each meeting — no cloud recording needed. Uses
your pasted `zoom.us` cookies; no browser login.

> **How to run these tools:** use the Bash tool —
> `sophonic tool <NAME> --args-json '<JSON kwargs>'`. Prints JSON, no LLM key.

## Tools

- `zoom_notes(limit)` — Recent AI meeting notes: `{id, title, meeting, date, link, is_meeting_note}`.
- `zoom_note(doc_id)` — The note content (Key Outcomes, Decisions, Action Items, …).
- `zoom_save_note(doc_id, title)` — Save a note as an Obsidian meeting note (backlinked in the daily note).

## Examples

```bash
sophonic tool zoom_notes --args-json '{"limit":10}'
sophonic tool zoom_save_note --args-json '{"doc_id":"PUB4Gms1RyKnVL_rSUuUBw"}'
```

Typical flow: `zoom_notes` to find the meeting's `id`, then `zoom_save_note` with that id.

## Auth

If a result contains `{"needs_auth": true}`, the Zoom cookies are missing/expired. Tell
the user to log in to `zoom.us`, copy the session cookies, and run
`sophonic config set-secret ZOOM_COOKIES --stdin`. Zoom cookies expire fairly quickly.

## When to use

When the user asks about a recent meeting, its summary, decisions, or action items.
