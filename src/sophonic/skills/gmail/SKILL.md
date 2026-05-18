---
name: gmail
description: Read Gmail messages — unread summaries, search, and thread detail. Trigger when the user asks about email.
tools:
  - gmail_unread
  - gmail_search
  - gmail_thread
---

# Gmail

Read-only access to the user's Gmail account.

## Tools

- `gmail_unread(max_results)` — Return up to `max_results` unread messages as `{id, subject, from, date, snippet}`.
- `gmail_search(query, max_results)` — Search with Gmail query syntax (e.g. `from:boss@example.com after:2026/05/01`).
- `gmail_thread(thread_id)` — Return the full thread body for a thread ID from a previous result.

## When to use

- `gmail_unread` for "what's in my inbox" questions.
- `gmail_search` when the user names a sender, subject, or date range.
- `gmail_thread` to read the body of a specific message.

## Auth

Requires `sophonic auth google`. Surface auth errors with that instruction.
