---
name: obsidian
description: Read and write the user's Obsidian vault directly — daily notes, tasks, rollover, sections, and meeting notes. Use whenever the user mentions tasks, to-dos, notes, their daily note, meetings, or vault content. This is a pure skill; you edit markdown files yourself with Read/Write/Edit/Glob/Grep — there is no tool or API.
---

# Obsidian vault

You operate the user's Obsidian vault as plain markdown files, using your own
Read/Write/Edit/Glob/Grep tools. There is no Obsidian API and no helper binary — the
vault is just files on disk. **Always Read a note before editing it**, and preserve
everything you are not deliberately changing.

## Resolve the vault root (once per session)

The vault path is configured, not assumed:

1. If `$SOPHONIC_VAULT` is set, use it.
2. Otherwise run:
   `uv run python "${CLAUDE_PLUGIN_ROOT}/scripts/config.py" get vault.path`
   and use the returned value.

Other configured locations (same `config.py get`): `vault.daily_dir` (default
`Daily`), `vault.daily_prefix` (default `DAILY-`), `vault.meetings_dir` (default
`Work/Meetings`). Below, `<vault>` means the resolved root.

## Daily notes

- Path: `<vault>/<daily_dir>/<daily_prefix>YYYY-MM-DD.md` — e.g.
  `<vault>/Daily/DAILY-2026-08-13.md`.
- If today's note is missing, create it from this exact template (blank line after the
  tag, one blank line under each heading):

  ```markdown
  # DAILY 2026-08-13
  #sophonic

  ## Tasks

  ## Notes
  ```

## Task lines (Obsidian Tasks emoji format)

Match this format exactly so the Obsidian Tasks plugin parses them:

```
- [ ] <text> <priority?> 📅 YYYY-MM-DD <#tag …>
```

- Priority marker (optional): high `⏫`, medium `🔼`, low `🔽`. Omit for none.
- Due date (optional): `📅 YYYY-MM-DD`.
- Tags (optional): `#tag` tokens at the end, e.g. `#zoom`, `#slack`, `#gtask`.
- Completed: `- [x] <text> … ✅ YYYY-MM-DD` (append the ✅ + completion date).

Example: `- [ ] Email Dana the deck ⏫ 📅 2026-08-14 #followup`

## Where things go

- **Tasks** → directly under the `## Tasks` heading (insert as the first line after it).
- **Notes / backlinks** → under `## Notes`.
- **Grouped tasks** (e.g. meeting action items) → a `## Meeting Action Items` section,
  placed *before* `## Notes`, with a `### ` subheading per group and checkbox items
  beneath it (see the daybrief skill).
- **Refreshable snapshots** (e.g. a Slack summary) → a `## <Name>` section you *replace*
  in place on each run rather than append to.

## Core operations

**Add a task.** Read today's note; insert the formatted task line immediately after
`## Tasks`. If the note lacks `## Tasks`, append the heading + line at the end.

**List / scan tasks.** Open task lines match `- [ ] `. The due date is the `📅
YYYY-MM-DD` token. Use Grep across `<vault>/**/*.md` for vault-wide scans (e.g. tasks
due today, overdue, or due before a date).

**Complete a task.** Change its `- [ ] ` to `- [x] ` and append ` ✅ <today>`.

**Rollover (idempotent — read-diff-write).** Carry unfinished tasks forward:

1. Find the most recent daily note *strictly before* the target day (usually today) —
   glob `<daily_dir>/<daily_prefix>*.md`, parse the ISO date from each name, pick the
   latest one before the target. A missing "yesterday" falls back to the last day the
   user actually took notes.
2. Collect its incomplete (`- [ ] `) lines.
3. Read the target note and add **only** the lines not already present verbatim.
   Re-running must add nothing — dedupe on the exact line text.

**Meeting note.** File a transcript at
`<vault>/<meetings_dir>/YYYY-MM-DD - <Title>.md` with this shape, then add a backlink
`- [[<meetings_dir>/YYYY-MM-DD - <Title>]]` under `## Notes` in today's daily note (only
if that backlink isn't already there):

```markdown
---
source: zoom
recorded_at: 2026-08-13
tags: [sophonic]
---

# <Title>

<content>
```

**Search.** Use Grep over `<vault>/**/*.md` (ripgrep) and report `file:line`.

## Rules

- Read before write; never clobber content you didn't mean to change.
- Keep task formatting byte-exact (the emoji format above) — the Tasks plugin depends on it.
- Dedupe every append against what's already in the note so re-runs are safe.
- Related: [[reminders]], [[daybrief]].
