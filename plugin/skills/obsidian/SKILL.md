---
description: Read and write the Obsidian vault — daily notes, tasks, and meeting notes. Use when the user mentions tasks, to-dos, notes, or their vault.
---

# Obsidian

Read and write the user's Obsidian vault through the `sophonic` CLI.

> **How to run these tools:** use the Bash tool. Invoke one tool with
> `sophonic tool <NAME> --args-json '<JSON kwargs>'` — it prints a JSON result and
> needs no API key. Run `sophonic tools` to list everything currently available
> (feature flags in `~/.sophonic/config.toml` gate which tools exist).

## Tools

- `obsidian_add_task(text, due, priority, tags, note_date)` — Add a task under `## Tasks`. `priority`: "high" | "medium" | "low".
- `obsidian_list_tasks(filter, target_date)` — Scan for tasks. `filter`: "all" | "due_today" | "overdue" | "incomplete_yesterday" | "due_before:YYYY-MM-DD".
- `obsidian_incomplete_yesterday()` — Tasks due/present in yesterday's note but not completed.
- `obsidian_rollover(from_date, to_date)` — Copy incomplete tasks between daily notes. Idempotent.
- `obsidian_complete_task(file, line_text)` — Mark a task complete with ✅ today.
- `obsidian_daily_note(for_date)` — Full text of a daily note (created from template if missing).
- `obsidian_read_note(path)` — Read any note by vault-relative path.
- `obsidian_write_note(path, content)` — Overwrite a note by vault-relative path.
- `obsidian_append_note(path, content)` — Append to a note without overwriting.
- `obsidian_search(query, max_results)` — Full-text search; returns `{file, line, line_no}` per match.
- `obsidian_save_meeting_note(title, content, recorded_at, source)` — File a transcript under Work/Meetings and backlink it in today's note.

## Examples

```bash
sophonic tool obsidian_list_tasks --args-json '{"filter":"due_today"}'
sophonic tool obsidian_add_task --args-json '{"text":"Email Dana the deck","due":"2026-08-01","priority":"high"}'
sophonic tool obsidian_search --args-json '{"query":"Q3 roadmap","max_results":5}'
```

## Conventions

- Daily notes are `DAILY-YYYY-MM-DD.md` under `Daily/`.
- Tasks use Obsidian Tasks emoji format: `- [ ] Task text ⏫ 📅 YYYY-MM-DD #tag` (high ⏫, medium 🔼, low 🔽; completed `- [x] … ✅ YYYY-MM-DD`).
- Insert tasks under `## Tasks`, backlinks under `## Notes`.

## When to use

Whenever the user mentions tasks, to-dos, notes, meetings, or vault content. Always read before writing to avoid overwriting.
