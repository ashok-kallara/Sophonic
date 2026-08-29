---
name: gdrive
description: >
  Google Drive, read-only: (1) unresolved comments on Docs/Sheets where the user is
  @mentioned or assigned, and (2) full-text search across the content of Docs and
  Sheets. Use when the user asks "what comments am I mentioned in", "open comments on
  my docs", "where do I need to reply in Drive" — or "find the doc that mentions X",
  "search my Google Docs for Y", "what does that spreadsheet say about Z".
---

# Google Drive

Two independent read-only capabilities, both via thin fetch-scripts:

- **Comments** — unresolved comments where you're @mentioned or assigned. Prioritizes
  recent files; a full-Drive fallback exists but must be offered, never auto-run.
- **Content search** — full-text search across what your Docs/Sheets actually say, with
  an excerpt per match. Already covers everything you can see by default — no
  recent/full tiering needed here.

Use comments for "did I miss a reply"; use content search for "where did I write X" or
"which doc/sheet covers Y".

## Comments

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gdrive.py" mentioned-comments
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gdrive.py" mentioned-comments --days 7 --max-files 20
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gdrive.py" mentioned-comments --all
```

- `--days` — look back this many days for recently-modified files (default 30).
- `--max-files` — max number of Docs/Sheets to inspect (default 50, most-recently-modified
  first; default 2000 when `--all` is set).
- `--all` — **full scan.** Drops the day filter and paginates through every Doc/Sheet you
  can access, up to `--max-files`. Costs one extra API call per file (the Drive Comments
  API has no way to search across a whole Drive in one call), so it's meaningfully
  slower than the default pass — **never run this without asking first.**

Default to the plain `mentioned-comments` call (recent files only). Two things worth
knowing before you report "nothing found":

- Adding a comment does **not** update a file's `modifiedTime` — that field only tracks
  content edits. A brand-new mention on an old, otherwise-untouched doc is invisible to
  the day-bounded pass no matter how large `--days` is.
- If the recent pass returns an empty list (or a `{"message": ...}` no-results stub),
  say so plainly and then **ask** whether to run a full scan (`--all`) — don't run it
  automatically. It's slower and burns far more of the user's API quota, so the user
  should decide whether that trade-off is worth it for this particular question.

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

## Content search

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gdrive.py" search-content --query "Q3 budget"
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gdrive.py" search-content --query "Q3 budget" --max-files 10 --context-chars 300
```

- `--query` — the text to search for.
- `--max-files` — max matching files to return (default 20).
- `--context-chars` — characters of context kept on each side of the match in the
  excerpt (default 200).

This uses Drive's own `fullText contains` search — one indexed query that already
covers every Doc/Sheet you can see, most recently modified first. Unlike comments,
there's no recent-vs-full-scan decision to make here; it's exhaustive by default.
Docs are read via Drive's own export; Sheets are read via the Sheets API across
**every tab**, not just the first one (Drive's own spreadsheet export is first-tab-only,
which is why this needs a separate scope — see Auth below).

Returns `[{file_id, file_name, file_type, file_link, excerpt}]`. `excerpt` is a window of
text around the match (Drive's search is tokenized/fuzzy, not literal substring, so if the
exact query text never reappears in the exported content, `excerpt` falls back to a
leading preview instead). A file whose content couldn't be fetched carries
`excerpt: null` plus `needs_auth`/`error` on that entry instead of failing the whole
search — expected while only one of the two Drive scopes has been granted (see Auth).

## Auth

Comments need `drive.readonly`; content search also needs `spreadsheets.readonly` (for
full multi-tab Sheets reading) — both are broader/additional grants beyond the other
Google skills (calendar/gmail/tasks). If a result — or a per-file entry in a
content-search list — is `{"needs_auth": true, "run": "..."}`, tell the user to run the
returned `run` command in their terminal (it re-consents with every scope Sophonic
uses). Setup: [[setup]].

A `{"error": "..."}` mentioning an API not being enabled (rather than a scope) means the
Drive or Sheets API needs enabling in the Google Cloud project the OAuth client belongs
to — the message names which one and links directly to it.
