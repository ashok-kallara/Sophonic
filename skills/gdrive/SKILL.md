---
name: gdrive
description: >
  Fetch open (unresolved) comments on Google Docs and Sheets where the authenticated
  user is @mentioned or assigned. Use when the user asks "what comments am I mentioned
  in", "open comments on my docs", "where do I need to reply in Drive", "any unresolved
  comments for me", or similar questions about Google Drive document comments.
---

# Google Drive Comments

Read-only list of unresolved Google Doc and Sheet comments where you are @mentioned
or assigned, via a thin fetch-script.

## Run

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gdrive.py" mentioned-comments
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gdrive.py" mentioned-comments --days 7 --max-files 20
```

- `--days` — look back this many days for recently-modified files (default 30).
- `--max-files` — max number of Docs/Sheets to inspect (default 50, most-recently-modified first).

## Return shape

Returns `[{file_id, file_name, file_type, file_link, comment_id, author, author_email,
content, created, modified, is_assigned, mentions, reply_count}]`.

- `file_type` — `"document"` or `"spreadsheet"`.
- `file_link` — opens the file in the browser. The Drive API does not expose per-comment
  deep links, so this is a file-level URL.
- `is_assigned` — true when the comment was explicitly assigned to you via the assign
  button. Assigned comments also appear in Google Tasks (see [[gtasks]]); the Tasks entry
  carries the document link in its `links[]` array.
- `mentions` — list of email addresses @mentioned in the comment (properly
  autocomplete-selected mentions; informal `@name` text without autocomplete is not
  captured by the API).
- `author_email` — may be empty if the author's email is not visible to you.
- `reply_count` — number of replies on the comment thread.

When presenting results, group by file and format each comment as:
**[file_name](file_link)** — `author`: comment excerpt (`created`)

## Note on scope

This skill requires the `drive.readonly` OAuth scope, which grants read access to all
your Google Drive file contents. This is a broader grant than the other Google skills
(calendar/gmail/tasks). The `needs_auth` response includes a command to re-consent
with this scope added.

## Auth

Needs the `drive.readonly` scope. If the result is
`{"needs_auth": true, "run": "..."}`, the token lacks that scope — tell the user to
run the returned `run` command in their terminal (it adds all four Google scopes and
re-consents). Setup: [[setup]].
