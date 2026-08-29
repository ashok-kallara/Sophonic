---
name: meeting-recap
description: >
  Pull today's Zoom AI Companion meeting summaries into today's Obsidian daily note as a
  `## Meeting Recaps` section (idempotent — meetings already recapped are skipped without
  refetching). Use when the user says "meeting recap", "recap my meetings", "what
  happened in my meetings today", "summarize today's meetings", or asks to add today's
  Zoom summaries to the daily note.
---

# Meeting recap

Capture the **AI Companion summary** of each of today's Zoom meetings into today's daily
note, verbatim (trimmed) — not a rewrite, not the transcript, not the action items.

Scope: Zoom only. Target: inline in today's daily note under `## Meeting Recaps`, each
meeting written as its own **collapsed callout** so a day with several meetings doesn't
turn into a wall of text — expand the one you want to read. Action items are **not**
this skill's job — [[start-my-day]] already turns those into tasks under
`## Meeting Action Items`, and the two sections coexist on the same note without
conflict.

Fetching a note's content is expensive (~6s of browser page-load per meeting), so this
skill **checks the note before it fetches**: any meeting whose link is already under
`## Meeting Recaps` is skipped entirely — no `note --id` call is made for it. Re-running
on the same day should therefore be fast, idempotent, and change nothing for meetings
already captured.

## Run

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" check-auth
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" notes --limit 50
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" note --id <doc_id>
```

`notes` is one relatively cheap call; `note --id` is one slow call **per meeting**. See
[[zoom]] for the full return shapes. Raising `--limit` costs nothing extra — the script
captures the whole notes-list response before truncating to `limit` client-side, so 50 is
a safe default even on a light day.

## Procedure

### 1. Resolve the note

Resolve `<vault>`, `daily_dir`, and `daily_prefix` exactly as [[obsidian]] specifies
(`$SOPHONIC_VAULT`, else `config.py get vault.path` / `vault.daily_dir` /
`vault.daily_prefix`) — never assume a folder name. Today's note is
`<vault>/<daily_dir>/<daily_prefix>YYYY-MM-DD.md`; create it from the [[obsidian]]
template if it doesn't exist yet.

**Read the whole note now.** You need its current contents for step 3, and you must
never edit a note you haven't read.

### 2. List today's meetings

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" notes --limit 50
```

Keep a note as a candidate only when **both** hold:

- `date` equals today's ISO date (`notes` has no server-side date filter — filtering is
  on you), and
- `is_meeting_note` is `true` (skip hand-authored Zoom Docs — this skill copies whole
  body text, so an unfiltered manual doc would dump arbitrary content into the note).

Entries with `date: null` have no timestamp embedded in their title, so they can't be
confirmed as today's — **skip them, but count them** and mention the count in your final
report; a silent drop in a command whose whole job is "today" would look like a bug.

Sort surviving candidates by the `HH:MM` embedded in `title` (ascending) so recaps land
in meeting order; fall back to listing order when no time is present.

If nothing survives, say so plainly ("no Zoom meetings found for today") and stop — this
is a normal outcome, not an error.

### 3. Pre-check each candidate BEFORE fetching it

This runs **per meeting, before any `note --id` call.** Do not batch-fetch first and
dedupe after — that defeats the entire point of this step.

For each candidate, compute its dedup key: its `link`, or
`https://docs.zoom.us/doc/<id>` when `link` is null (the same URL template the script
itself builds internally, so the two always agree). If that key already appears anywhere
under `## Meeting Recaps` in the note you read in step 1, **skip this meeting — issue no
`note --id` call for it** and count it as "already present."

Only the surviving candidates move on to step 4.

### 4. Fetch and trim each survivor

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/zoom.py" note --id <doc_id>
```

`text` is one scraped blob — there's no separate summary field, so you trim it yourself
as you read it. **Confirmed by fetching real notes while building this skill:** every
Zoom AI Companion doc renders in three parts, in this order, and all three matter:

1. The doc **title**, then a plain-text **outline/table-of-contents** block that lists
   the doc's heading names (e.g. `Key Outcomes`, `Action Items`) with no formatting —
   these are *not* real headings and must not be treated as ones.
2. The **real content**, whose real headings are the same vocabulary words but each
   carries an invisible trailing zero-width space (`​`) that the TOC copies lack.
   This is the only reliable way to tell a real heading from its TOC mention.
3. A constant **Zoom Docs UI/tutorial footer** (toolbar labels like `Regenerate`,
   `Templates`, a "Check out these productivity-boosting features" help widget, then a
   `📚 Tutorial` list of "How to …" article titles) — page furniture, not meeting
   content, appended after the real content ends.

Trim in this order:

**a. Find where real content starts.** Scan for the first line whose stripped text ends
with a zero-width space (`​`) and whose text with that character removed matches one
of the heading words below. Discard everything before that line — this removes the title
and the TOC block in one step. If no line has that marker anywhere (a doc rendered
without it), fall back to keeping everything from the first line after the title.

**b. Find where real content ends.** Scan forward from there for the first line that is
exactly `Regenerate`, or a line that reads "Check out these productivity-boosting
features", or a line that is exactly `📚 Tutorial`. Discard that line and everything after
it — it's Zoom's app chrome, not the meeting.

**c. Within what remains, walk lines top-to-bottom with a keep/drop state that starts as
keep.** A line counts as a heading only if, after stripping leading `#`/`**`, a trailing
`:`, a trailing zero-width space (`​`), and whitespace, its lowercased form *exactly
equals* one of these — a body sentence that merely contains the words is not a heading
and must not flip the state:

- **Keep-headings** → switch state to keep, and re-emit the line as `#### <original
  heading text, zero-width space stripped>`: `quick recap`, `recap`, `summary`,
  `key outcomes`, `outcomes`, `overview`, `details`, `notes`, `decisions`, `discussion`,
  `attendees`.
- **Drop-headings** → switch state to drop, emit nothing: `transcript`, `manual notes`,
  `recording`, `action items`, `action item`, `next steps`, `next step`, `follow-ups`,
  `follow ups`, `followups`, `to-dos`, `todos`.

Non-heading lines inherit the current state. **You must resume on the next
keep-heading — do not just cut at the first drop-heading and stop.** Zoom AI Companion
commonly orders sections *Quick Recap → Next Steps → Summary*; a single cut there would
throw away the Summary, the most valuable block. (Step (a) already skips the doc's outer
`Action Items` TOC mention, so this state machine only ever sees the real body — but keep
the resume rule anyway in case a doc has more than one real drop/keep transition.)

Then, on the surviving text:

- Drop a leading line that's just the note's `title` or the listing's `meeting` name —
  the `###` subheading you're about to write already says it.
- Strip a trailing zero-width space from every kept line, not just headings — it's
  invisible but bloats the raw markdown and can throw off the ~40-character guard below.
- Strip orphaned footnote/citation marks — short runs of zero-width space or similarly
  invisible characters glued to a digit (e.g. a stray `¹²`-style reference with no
  footnote list attached in this scrape) — they're meaningless once orphaned.
- **Bullets render as a marker on its own line, then a blank line, then the item's text
  on the next line** (confirmed by fetching a real note) — not marker-and-text on one
  line. When you see a line that is *only* `•`/`*` (top-level) or `◦` (nested), merge it
  with the next non-blank line into one `- <text>` (or `  - <text>` for `◦`) list item,
  and drop the blank line that separated them. If a marker and its text ever *do* appear
  on the same line, convert that directly. **Never emit `- [ ]`** in this section — a
  checkbox here would get scraped by the Obsidian Tasks plugin.
- If, despite (a)/(b), a run of lines still looks like transcript speaker stamps
  (repeated `Name HH:MM` or `HH:MM:SS`), drop that run too.
- Cap each recap at ~150 lines / ~8000 characters. If you truncate, end the block with
  `_Truncated — full recap in the linked Zoom doc._`
- **If the trimmed content is under ~40 characters, write nothing for that meeting.** An
  empty block would look "already present" on the next run and permanently skip a
  meeting whose AI summary simply hasn't finished generating yet — count it as "recap not
  ready" instead and mention it in your report.

### 5. Write

Wrap each survivor's trimmed recap in a **collapsed Obsidian callout** so the daily note
doesn't turn into a wall of meeting text — one fold per meeting, so any one of them can
be expanded without opening the rest. Prefix **every** line of the trimmed recap with
`> ` (a blank line becomes a bare `>`, not truly empty — an unprefixed blank line ends
the callout early in Obsidian's parser):

```markdown
> [!summary]- [<meeting> — <date>](<link>)
> #### Key Outcomes
>
> <trimmed recap, one `> ` per line, blank lines as a bare `>`>
```

- `[!summary]-` is a built-in Obsidian callout type (aliased to "abstract"/"tldr") with
  the `-` fold indicator right after the closing `]` — that's what makes it render
  **collapsed by default** on every write, not just foldable by clicking. Swap `summary`
  for another built-in type (e.g. `note`) for a different icon/color; the `-` is what
  controls the collapse.
- Append the whole callout block under `## Meeting Recaps`, one per meeting.
- **Append-only.** Never rewrite or replace the whole section — existing callout blocks
  stay byte-identical. New blocks go at the end of the section.
- **Placement.** If `## Meeting Recaps` doesn't exist yet, insert it immediately
  **before** `## Notes` (the last heading in every real daily note so far, even though
  earlier sections' order has drifted from the documented template). If there's no
  `## Notes` heading, append the new section at the end of the note instead.
- Preserve everything else in the note exactly as it was. Existing dedup logic (step 3)
  is unaffected — the link is still plain text inside the callout's title line, so a
  substring check for it still works.

### 6. Report

State: how many recaps were added (with meeting names), how many were skipped as
already present, how many were skipped for having no confirmable date, how many had no
summary ready yet, and any error or auth gap along with its fix command.

## Auth and errors

Every failure mode reports and stops cleanly for that meeting — never half-write a block.

- `{"needs_auth": true, "run": "..."}` from `notes` or `note` (or `check-auth` reporting
  an expired session): tell the user to run the returned command **in their own
  terminal** — paste the `Cookie:` request-header value from https://zoom.us (DevTools →
  Network) into `uv run python scripts/config.py set-secret ZOOM_COOKIES --stdin` — and
  write nothing. Setup: [[setup]].
- `[{"message": "No Zoom notes found"}]`: say Zoom returned no notes at all (often an
  expired session that silently didn't redirect) and suggest running `check-auth`.
- `{"error": "..."}` from any call: report it verbatim. If it mentions
  Playwright/Chromium, point at `uv run playwright install chromium`.
- Notes returned but none match today: report it plainly and change nothing — a normal
  outcome, not an error.
- A single `note --id` call failing: report that one meeting as failed and continue with
  the rest; don't abort the whole run.

## Refreshing a recap

Presence of the link under `## Meeting Recaps` means "done" for that day, permanently —
a meeting is never refetched automatically, even if Zoom later edits or regenerates its
summary. To force a refresh, delete that meeting's callout block from the note and
re-run; only then is that meeting fetched again. This tradeoff is what makes the
check-before-fetch saving real — a compare-and-update model would require refetching
everything every time.

Related: [[zoom]], [[obsidian]], [[start-my-day]].
