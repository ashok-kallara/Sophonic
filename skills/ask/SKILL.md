---
name: ask
description: >
  Answer an ad-hoc question by searching across all configured Sophonic sources —
  Obsidian vault, Google Tasks, Google Drive comments, Slack, Gmail, Google Calendar,
  Zoom notes, GitLab. Use when the user asks "find", "search", "where is", "do I have
  any", "what do I know about", "show me anything about", or any open-ended question
  that might span multiple tools.
---

# Ask

Answer an ad-hoc question by fanning out to every configured source, then
synthesizing the results in-model. **Read-only** — report findings with citations
and links; never modify the vault unless the user explicitly asks in a follow-up.

## Guiding principles

- **Independent sources.** Treat each source as optional: if one is unconfigured,
  unauthenticated (`{"needs_auth": true, "run": "..."}`), or errors, note it and
  keep going — never abort the whole search.
- **Keyword inference.** Derive search terms from the question; try synonyms and
  alternate spellings when a first pass returns nothing.
- **Selective depth.** For Gmail and Zoom, fetch full thread/note content only when
  a summary strongly suggests relevance — keep Bash calls lean.
- **Synthesize in-model.** Write the answer yourself from the raw results. Do not
  shell out to any LLM.

## Procedure

### 1. Understand the question

Identify the topic, keywords, and any time/person/project scope. Unless the question
names a specific source, search them all. Map the question's time reference (e.g.
"this week", "last month") to concrete dates for time-scoped fetchers.

### 2. Obsidian

Use Grep over `<vault>/**/*.md` with the question keywords (and synonyms). Report
matching file paths, line numbers, and a short surrounding snippet. Obsidian is often
the richest source — try two or three keyword variants before concluding nothing is
there. Vault root: `$SOPHONIC_VAULT` or `uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/config.py" get vault.path`.

### 3. Google Tasks

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gtasks.py" list
```

Returns `[{id, title, notes, due, list, list_id, link, links}]`. Filter in-model to
tasks whose title or notes contain the topic. Report matching tasks with list name,
due date, and the `link` URL when present.

### 4. Gmail

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gmail.py" search --query "<derived gmail query>" --max 10
```

Construct an appropriate Gmail query (e.g. `subject:budget after:2026/01/01`).
If a snippet looks relevant, fetch the full thread:

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gmail.py" thread --thread-id <thread_id>
```

Report subject, sender, date, and a snippet or key excerpt.

### 5. Slack

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/slack.py" search --query "<topic>"
```

Returns `[{text, channel, user, ts, permalink}]`. Report matching messages with
channel, user, and the permalink.

### 6. Google Drive comments

If the question is about comments, mentions, or docs/sheets needing a reply:

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gdrive.py" mentioned-comments --days 30
```

Returns unresolved comments where the user is @mentioned or assigned. Filter in-model
to the topic and report the file name, author, excerpt, and `file_link`.

### 7. Google Calendar

If the question has a time scope (e.g. "meetings this week", "what's on Thursday"):

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gcal.py" events-range --start YYYY-MM-DD --end YYYY-MM-DD
```

Otherwise use `events-today`. Report matching events with start time and link.

### 8. Zoom notes

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" notes
```

Scan the summaries. If a note title looks relevant, fetch its content:

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" note --id <id>
```

Report relevant meetings, key discussion points, and action items.

### 9. GitLab

Use the `gitlab` skill to search issues, merge requests, and wiki pages for the topic.
Skip this step if GitLab is not configured (`features.gitlab = false` or no
`GITLAB_TOKEN`).

### 10. Synthesize

Write a concise answer grouped by source:

- Which sources were searched and which were skipped (with reason).
- Results from each source: key details inline, citations as markdown links.
- A one-paragraph summary at the top if results span multiple sources.
- If nothing was found anywhere, say so explicitly.

## Auth

On `{"needs_auth": true, "run": "..."}` for any source: tell the user to run the
returned `run` command in their terminal, skip that source, and continue.
Setup: [[setup]].
