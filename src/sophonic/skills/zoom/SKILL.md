---
name: zoom
description: Fetch and save Zoom meeting transcripts from the Zoom web portal. Trigger when the user asks about a recent meeting recording or transcript.
tools:
  - zoom_transcripts
  - zoom_transcript
  - zoom_save_transcript
---

# Zoom

Browser-scraper access to the Zoom web portal for meeting transcripts.

## Tools

- `zoom_transcripts(limit)` — List recent recorded meetings: `{meeting_id, topic, date}`.
- `zoom_transcript(meeting_id)` — Return the full transcript text for a meeting.
- `zoom_save_transcript(meeting_id, title)` — Fetch transcript and save it as an Obsidian meeting note via `obsidian_save_meeting_note`.

## Auth

If `{"needs_auth": true}` is returned, tell the user to run `sophonic auth zoom`.

## When to use

Use when the user asks about a recent meeting or wants to review what was discussed. Always save with `zoom_save_transcript` so transcripts are searchable in the vault later.
