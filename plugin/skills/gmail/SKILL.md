---
description: Read Gmail — unread summaries, search, and full threads. Use when the user asks about email.
---

# Gmail

Read-only access to the user's Gmail account.

> **How to run these tools:** use the Bash tool —
> `sophonic tool <NAME> --args-json '<JSON kwargs>'`. Prints JSON, no API key.

## Tools

- `gmail_unread(max_results)` — Up to `max_results` unread messages as `{id, subject, from, date, snippet}`.
- `gmail_search(query, max_results)` — Gmail query syntax (e.g. `from:boss@example.com after:2026/05/01`).
- `gmail_thread(thread_id)` — Full thread body for a `thread_id` from a previous result.

## Examples

```bash
sophonic tool gmail_unread --args-json '{"max_results":20}'
sophonic tool gmail_search --args-json '{"query":"from:boss@example.com after:2026/07/01","max_results":10}'
sophonic tool gmail_thread --args-json '{"thread_id":"18f9c2a1b3d4e5f6"}'
```

## When to use

- `gmail_unread` for "what's in my inbox".
- `gmail_search` when the user names a sender, subject, or date range.
- `gmail_thread` to read a specific message body.

## Auth

Requires `sophonic auth google`. Surface auth errors with that instruction.
