---
name: gmail
description: Read the user's Gmail (read-only) — unread messages, follow-ups awaiting a reply, search with Gmail query syntax, or a full thread with bodies. Use when the user asks about email, unread mail, or a specific message/thread.
---

# Gmail

Read-only Gmail via a thin fetch-script.

## Run

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gmail.py" unread --max 20
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gmail.py" search --query "is:unread from:boss@acme.com" --max 10
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gmail.py" followups --days 2 --max-items 20
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gmail.py" thread --thread-id <thread_id>
```

- `unread` / `search` return message summaries `{id, thread_id, subject, from, date, snippet}`.
- `search` uses Gmail query syntax (`is:unread`, `from:`, `subject:`, `after:`, …).
- `followups` — inbox threads from the last N days whose most recent message isn't from
  me (i.e. still awaiting my reply), excluding chats/promotions/social. Returns
  `{"items": [...]}`, each `{thread_id, subject, from, date, snippet, link}`.
- `thread` returns every message in the thread with decoded `body` text — use it when
  you need the actual content, not just snippets.

## Auth

Needs Google OAuth. On an auth error, tell the user to run
`uv run python scripts/auth.py google` in their terminal. Setup: [[setup]].
