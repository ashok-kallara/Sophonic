---
name: slack
description: Read Slack via the desktop app's local session (read-only) — unread, an unread digest split into actionable vs informational, follow-ups needing a reply, and message search. Use when the user asks "what did I miss on Slack", about mentions/DMs, or to search Slack.
---

# Slack

Reads the signed-in **Slack desktop app**'s local session (no browser, no admin token)
and calls the Slack Web API, via a thin fetch-script.

## Run

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/slack.py" unread
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/slack.py" digest --per-channel 8 --max-channels 25
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/slack.py" followups --days 2
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/slack.py" search --query "deploy freeze"
```

- `unread` — unread channels/group-DMs/DMs as `{channel, type, mentions, id}`.
- `digest` — unread *with content*, split into `actionable` (DMs / @-mentions) and
  `informational` (other channels), each carrying recent messages, latest snippet,
  mention count, and a permalink. The [[daybrief]] skill summarizes the informational
  half into the note.
- `followups` — from the last N days: @-mentions and DMs you haven't replied to, plus
  saved-for-later messages — the things that likely still need action.
- `search` — `search.messages` results `{text, channel, user, ts, permalink}`.

## Auth

macOS only (reads the app's encrypted session via the Keychain). If a result contains
`{"needs_auth": true}`: make sure the Slack desktop app is installed and signed in, then
have the user run `uv run python scripts/auth.py slack` in their terminal and approve the
one-time Keychain prompt for *Slack Safe Storage*. If it still fails they may need to set
`slack.workspace_host` or the `SLACK_XOXC_TOKEN` secret. Setup: [[setup]].
