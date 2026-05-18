---
name: obsidian
description: Read and write the Obsidian vault — daily notes, tasks, and meeting transcripts. Trigger when the user mentions tasks, reminders, notes, or meetings.
tools:
  - obsidian_add_task
  - obsidian_list_tasks
  - obsidian_incomplete_yesterday
  - obsidian_rollover
  - obsidian_complete_task
  - obsidian_daily_note
  - obsidian_read_note
  - obsidian_write_note
  - obsidian_append_note
  - obsidian_search
  - obsidian_save_meeting_note
---

# Obsidian

Read and write the user's Obsidian vault via these sophonic tools.

## Tools

- `obsidian_add_task(text, due, priority, tags, note_date)` — Add a task line under `## Tasks` in a daily note. `priority`: "high", "medium", or "low".
- `obsidian_list_tasks(filter, target_date)` — Scan vault for tasks. `filter`: "all" | "due_today" | "overdue" | "incomplete_yesterday" | "due_before:YYYY-MM-DD".
- `obsidian_incomplete_yesterday()` — Return tasks due or present in yesterday's note but not completed.
- `obsidian_rollover(from_date, to_date)` — Copy incomplete tasks from one daily note into another. Idempotent.
- `obsidian_complete_task(file, line_text)` — Mark a task complete with ✅ today's date.
- `obsidian_daily_note(for_date)` — Return the full text of a daily note (creates from template if missing).
- `obsidian_read_note(path)` — Read any note by vault-relative path.
- `obsidian_write_note(path, content)` — Write (overwrite) a note by vault-relative path.
- `obsidian_append_note(path, content)` — Append to a note without overwriting.
- `obsidian_search(query, max_results)` — Full-text search; returns `{file, line, line_no}` per match.
- `obsidian_save_meeting_note(title, content, recorded_at, source)` — File a meeting transcript under Work/Meetings and backlink it from today's daily note under `## Notes`.

## Conventions

- Daily notes are named `DAILY-YYYY-MM-DD.md` and live under `Daily/`.
- Tasks use Obsidian Tasks emoji format: `- [ ] Task text ⏫ 📅 YYYY-MM-DD #tag`
  - Priority emojis: high = ⏫, medium = 🔼, low = 🔽
  - Completion: `- [x] Task text ✅ YYYY-MM-DD`
- Always insert tasks under `## Tasks` and backlinks under `## Notes`.
- Meeting notes are stored under the path in `~/.sophonic/config.toml` `vault.meetings_dir` (default: `Work/Meetings`).

## When to use

Use these tools whenever the user mentions tasks, to-dos, notes, meetings, or asks about their vault content. Always read before writing to avoid overwriting content.
