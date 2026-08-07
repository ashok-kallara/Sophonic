"""Obsidian vault operations — pure filesystem, no Obsidian API needed."""

from __future__ import annotations

import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sophonic.paths import daily_note_path, meetings_dir, vault_root

# ── Task-line constants (Obsidian Tasks emoji format) ─────────────────────────

_INCOMPLETE_RE = re.compile(r"^- \[ \] .+", re.MULTILINE)
_DUE_RE = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")
_DONE_RE = re.compile(r"^- \[x\] .+", re.MULTILINE)

# ── Daily note helpers ────────────────────────────────────────────────────────

def ensure_daily_note(for_date: date | None = None) -> Path:
    """Return path to the daily note, creating it from template if missing."""
    from sophonic.skills import template as _template
    path = daily_note_path(for_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        d = for_date or date.today()
        path.write_text(
            _template("obsidian", "daily", date=d.isoformat()),
            encoding="utf-8",
        )
    return path


def get_daily_note(for_date: date | None = None) -> str:
    """Return the full text of a daily note (creates it if missing)."""
    return ensure_daily_note(for_date).read_text(encoding="utf-8")


# ── Enriched daily-note builder (schedule + rolled-over tasks + due-today agenda) ─

def _today_events(for_date: date) -> list[dict[str, Any]] | None:
    """Calendar events for a date. Returns None when Google is off, [] when unavailable."""
    if not load_config().features.google:
        return None
    try:
        from sophonic.tools.gcal import events_range
        return events_range(for_date, for_date)
    except Exception:
        # Calendar auth/network failure must never block note creation.
        return []


def _format_event_line(event: dict[str, Any]) -> str:
    start = str(event.get("start") or "")
    # Timed events look like 2026-08-03T09:00:00-04:00; all-day like 2026-08-03.
    when = start[11:16] if "T" in start else "all-day"
    title = event.get("title", "(No title)")
    line = f"- {when} — {title}"
    loc = event.get("location")
    return f"{line} @ {loc}" if loc else line


def _due_today_agenda(for_date: date, exclude: set[str]) -> list[str]:
    """Vault-wide tasks due on for_date, rendered as backlink references.

    Referenced (not copied as live checkboxes) so the same task isn't duplicated
    across notes for the Obsidian Tasks plugin. `exclude` skips task lines already
    carried into the note (e.g. rolled-over incompletes).
    """
    target = for_date.isoformat()
    lines: list[str] = []
    for t in list_tasks(filter="all"):
        if t.get("due") != target or t["text"] in exclude:
            continue
        body = re.sub(r"^- \[ \]\s*", "", t["text"]).strip()
        home = t["file"].removesuffix(".md")
        lines.append(f"- {body} ([[{home}]])")
    return lines


def build_daily_note(for_date: date | None = None) -> dict[str, Any]:
    """Create the daily note enriched with schedule, rolled-over tasks, and a due-today agenda.

    Idempotent: an existing note is never overwritten (returns created=False).
    """
    d = for_date or date.today()
    path = daily_note_path(d)
    if path.exists():
        return {
            "created": False,
            "file": str(path.relative_to(vault_root())),
            "message": "Daily note already exists",
        }

    ensure_daily_note(d)  # bare template

    # 1) Carry the last prior day's incomplete tasks forward into ## Tasks (live checkboxes).
    rolled = roll_over(to_date=d)
    rolled_texts = set(rolled.get("tasks", []))

    content = path.read_text(encoding="utf-8")

    # 2) Schedule — calendar events, inserted before ## Tasks (omitted if Google is off).
    events = _today_events(d)
    if events is not None:
        event_lines = [_format_event_line(e) for e in events] or ["- _No events_"]
        schedule = "## Schedule\n" + "\n".join(event_lines) + "\n\n"
        content = content.replace("## Tasks", schedule + "## Tasks", 1)

    # 3) Due-today agenda — references to tasks living elsewhere, inserted before ## Notes.
    agenda = _due_today_agenda(d, exclude=rolled_texts)
    if agenda:
        block = "## Due Today\n" + "\n".join(agenda) + "\n\n"
        content = content.replace("## Notes", block + "## Notes", 1)

    path.write_text(content, encoding="utf-8")
    return {
        "created": True,
        "file": str(path.relative_to(vault_root())),
        "events": len(events) if events is not None else 0,
        "rolled": rolled.get("rolled", 0),
        "due_today": len(agenda),
    }


# ── Task operations ───────────────────────────────────────────────────────────

def _format_task_line(
    text: str,
    due: date | None = None,
    priority: str | None = None,
    tags: list[str] | None = None,
) -> str:
    parts = [f"- [ ] {text.strip()}"]
    if priority:
        _priority_map = {"high": "⏫", "medium": "🔼", "low": "🔽"}
        parts.append(_priority_map.get(priority.lower(), ""))
    if due:
        parts.append(f"📅 {due.isoformat()}")
    if tags:
        parts.extend(f"#{t.lstrip('#')}" for t in tags)
    return " ".join(p for p in parts if p)


def add_task(
    text: str,
    due: date | str | None = None,
    priority: str | None = None,
    tags: list[str] | None = None,
    note_date: date | None = None,
) -> dict[str, Any]:
    """Append a task line under ## Tasks in today's (or given) daily note."""
    from sophonic.dates import parse_date

    due_date: date | None = None
    if isinstance(due, str):
        due_date = parse_date(due)
    elif isinstance(due, date):
        due_date = due

    line = _format_task_line(text, due_date, priority, tags)
    path = ensure_daily_note(note_date)
    content = path.read_text(encoding="utf-8")

    # Insert after ## Tasks heading; append at end if heading not found
    if "## Tasks" in content:
        content = content.replace("## Tasks\n", f"## Tasks\n{line}\n", 1)
    else:
        content = content + f"\n{line}\n"

    path.write_text(content, encoding="utf-8")
    return {"added": line, "file": str(path.relative_to(vault_root()))}


def list_tasks(
    filter: str = "all",
    target_date: date | str | None = None,
) -> list[dict[str, Any]]:
    """
    Scan the vault for task lines matching a filter.
    filter: "all" | "due_today" | "overdue" | "incomplete_yesterday" | "due_before:<YYYY-MM-DD>"
    """
    from sophonic.dates import parse_date, today, yesterday

    ref: date = today()
    if isinstance(target_date, str):
        parsed = parse_date(target_date)
        ref = parsed if parsed else ref
    elif isinstance(target_date, date):
        ref = target_date

    results = []
    vault = vault_root()

    for md_file in vault.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        for line in text.splitlines():
            if not re.match(r"^- \[ \]", line):
                continue
            due_match = _DUE_RE.search(line)
            due = date.fromisoformat(due_match.group(1)) if due_match else None

            if filter == "due_today" and due != today():
                continue
            elif filter == "overdue" and (due is None or due >= today()):
                continue
            elif filter == "incomplete_yesterday" and due != yesterday():
                continue
            elif filter.startswith("due_before:"):
                cutoff = date.fromisoformat(filter.split(":", 1)[1])
                if due is None or due >= cutoff:
                    continue

            results.append({
                "file": str(md_file.relative_to(vault)),
                "text": line,
                "due": due.isoformat() if due else None,
            })

    return results


def incomplete_yesterday() -> list[dict[str, Any]]:
    """Return tasks that were not completed and were due yesterday."""
    from sophonic.dates import yesterday
    ypath = daily_note_path(yesterday())
    results = []

    # Primary: yesterday's daily note unchecked lines
    if ypath.exists():
        vault = vault_root()
        for line in ypath.read_text(encoding="utf-8").splitlines():
            if re.match(r"^- \[ \]", line):
                due_match = _DUE_RE.search(line)
                results.append({
                    "file": str(ypath.relative_to(vault)),
                    "text": line,
                    "due": due_match.group(1) if due_match else None,
                    "source": "yesterday_note",
                })

    # Secondary: vault-wide tasks due yesterday that aren't done
    vault_wide = list_tasks(filter="incomplete_yesterday")
    seen = {r["text"] for r in results}
    for t in vault_wide:
        if t["text"] not in seen:
            t["source"] = "vault"
            results.append(t)

    return results


def _latest_prior_daily_note(before: date) -> date | None:
    """Date of the most recent daily note strictly before `before` (None if none exist)."""
    cfg = load_config().vault
    daily_dir = vault_root() / cfg.daily_dir
    if not daily_dir.is_dir():
        return None
    prefix = cfg.daily_prefix
    best: date | None = None
    for f in daily_dir.glob(f"{prefix}*.md"):
        stem = f.name[len(prefix):-len(".md")]
        try:
            d = date.fromisoformat(stem)
        except ValueError:
            continue
        if d < before and (best is None or d > best):
            best = d
    return best


def roll_over(
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    """Copy incomplete tasks from a prior daily note into to_date's note. Idempotent.

    When `from_date` is omitted, the most recent daily note *before* to_date is used —
    so a missing yesterday falls back to the last day you actually took notes.
    """
    from sophonic.dates import today

    dst_date = to_date or today()
    src_date = from_date if from_date is not None else _latest_prior_daily_note(dst_date)
    if src_date is None:
        return {"rolled": 0, "message": "No previous daily note found"}

    src_path = daily_note_path(src_date)
    if not src_path.exists():
        return {"rolled": 0, "message": f"No note for {src_date}"}

    src_text = src_path.read_text(encoding="utf-8")
    incomplete_lines = [l for l in src_text.splitlines() if re.match(r"^- \[ \]", l)]
    if not incomplete_lines:
        return {"rolled": 0, "message": "No incomplete tasks to roll over"}

    dst_path = ensure_daily_note(dst_date)
    dst_text = dst_path.read_text(encoding="utf-8")
    existing = set(dst_text.splitlines())

    to_add = [l for l in incomplete_lines if l not in existing]
    if not to_add:
        return {"rolled": 0, "message": "All tasks already present in destination"}

    if "## Tasks" in dst_text:
        block = "\n".join(to_add)
        dst_text = dst_text.replace("## Tasks\n", f"## Tasks\n{block}\n", 1)
    else:
        dst_text += "\n" + "\n".join(to_add) + "\n"

    dst_path.write_text(dst_text, encoding="utf-8")
    return {
        "rolled": len(to_add),
        "from": src_date.isoformat(),
        "to": dst_date.isoformat(),
        "tasks": to_add,
    }


def complete_task(file: str, line_text: str) -> dict[str, Any]:
    """Mark a matching task line as complete with ✅ today."""
    path = vault_root() / file
    if not path.exists():
        return {"error": f"File not found: {file}"}
    content = path.read_text(encoding="utf-8")
    done_suffix = f"✅ {date.today().isoformat()}"
    new_content = content.replace(
        line_text,
        line_text.replace("- [ ]", "- [x]", 1) + f" {done_suffix}",
        1,
    )
    if new_content == content:
        return {"error": "Task line not found in file"}
    path.write_text(new_content, encoding="utf-8")
    return {"completed": line_text, "file": file}


# ── Note operations ───────────────────────────────────────────────────────────

def upsert_section(heading: str, body: str, note_date: date | None = None) -> dict[str, Any]:
    """Insert or replace a `## {heading}` section in the daily note.

    Replaces the block from the heading up to the next `## ` heading (or end of file),
    so a refreshable snapshot (e.g. Slack unread) updates in place instead of stacking
    across runs. Creates the note (and section) if absent.
    """
    path = ensure_daily_note(note_date)
    content = path.read_text(encoding="utf-8")
    block = f"## {heading}\n{body.rstrip()}\n"

    lines = content.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.strip() == f"## {heading}"), None)

    if start is None:
        # Append the section, ensuring a blank-line separator before it.
        sep = "" if content.endswith("\n\n") or not content else ("\n" if content.endswith("\n") else "\n\n")
        path.write_text(content + sep + block + "\n", encoding="utf-8")
        return {"section": heading, "action": "inserted", "file": str(path.relative_to(vault_root()))}

    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    new_content = "".join(lines[:start]) + block + "".join(lines[end:])
    path.write_text(new_content, encoding="utf-8")
    return {"section": heading, "action": "replaced", "file": str(path.relative_to(vault_root()))}


def _insert_task_under(content: str, section: str, heading: str, task_line: str) -> str:
    """Insert task_line under `### {heading}` within `## {section}`, creating either if absent."""
    lines = content.splitlines()
    sec = f"## {section}"
    s = next((i for i, l in enumerate(lines) if l.strip() == sec), None)

    if s is None:
        # Create the section (with its first subheading + item), placed before ## Notes.
        block = [sec, heading, task_line, ""]
        notes_idx = next((i for i, l in enumerate(lines) if l.strip() == "## Notes"), None)
        if notes_idx is not None:
            lines[notes_idx:notes_idx] = block
        else:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend([sec, heading, task_line])
        return "\n".join(lines) + "\n"

    end = next((i for i in range(s + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    h = next((i for i in range(s + 1, end) if lines[i].strip() == heading), None)

    if h is None:  # add a new group subheading at the end of the section
        at = end
        while at - 1 > s and lines[at - 1].strip() == "":
            at -= 1
        lines[at:at] = [heading, task_line]
        return "\n".join(lines) + "\n"

    # append under the existing subheading, before the next ###/## boundary
    boundary = next((i for i in range(h + 1, len(lines)) if lines[i].startswith(("### ", "## "))), len(lines))
    at = boundary
    while at - 1 > h and lines[at - 1].strip() == "":
        at -= 1
    lines[at:at] = [task_line]
    return "\n".join(lines) + "\n"


def add_grouped_tasks(
    section: str,
    groups: list[dict[str, Any]],
    tags: list[str] | None = None,
    note_date: date | None = None,
) -> dict[str, Any]:
    """Append checkbox tasks under `## {section}`, grouped by `### {heading}` per group.

    `groups` is a list of {"heading": str, "items": [str]}. Append-only and deduped: an
    item already present anywhere in the note is skipped (preserves checked state and
    avoids duplicates on re-runs). Missing section/subheadings are created; the section is
    placed before ## Notes when present.
    """
    path = ensure_daily_note(note_date)
    tag_suffix = "".join(f" #{t.lstrip('#')}" for t in (tags or []))
    added = 0
    for g in groups:
        heading = f"### {g['heading']}"
        for item in g.get("items", []):
            content = path.read_text(encoding="utf-8")
            if item in content:
                continue
            path.write_text(
                _insert_task_under(content, section, heading, f"- [ ] {item}{tag_suffix}"),
                encoding="utf-8",
            )
            added += 1
    return {"section": section, "added": added}


def read_note(path: str) -> str:
    full = vault_root() / path
    if not full.exists():
        return ""
    return full.read_text(encoding="utf-8")


def write_note(path: str, content: str) -> dict[str, Any]:
    full = vault_root() / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return {"written": path}


def append_note(path: str, content: str) -> dict[str, Any]:
    full = vault_root() / path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(full, "a", encoding="utf-8") as f:
        f.write(content)
    return {"appended": path}


def search_vault(query: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Full-text search via ripgrep (falls back to Python grep if rg not found)."""
    vault = vault_root()
    try:
        result = subprocess.run(
            ["rg", "--json", "-l", query, str(vault)],
            capture_output=True, text=True, timeout=10,
        )
        files = [
            line for line in result.stdout.splitlines()
            if '"type":"match"' in line or line.endswith(".md")
        ]
        # rg --json: parse file matches
        import json
        hits = []
        for raw in result.stdout.splitlines():
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "match":
                hits.append({
                    "file": obj["data"]["path"]["text"].replace(str(vault) + "/", ""),
                    "line": obj["data"]["lines"]["text"].strip(),
                    "line_no": obj["data"]["line_number"],
                })
                if len(hits) >= max_results:
                    break
        return hits
    except FileNotFoundError:
        # rg not available — simple Python fallback
        hits = []
        for md_file in vault.rglob("*.md"):
            try:
                for i, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), 1):
                    if query.lower() in line.lower():
                        hits.append({
                            "file": str(md_file.relative_to(vault)),
                            "line": line.strip(),
                            "line_no": i,
                        })
                        if len(hits) >= max_results:
                            return hits
            except OSError:
                continue
        return hits


def save_meeting_note(
    title: str,
    content: str,
    recorded_at: date | None = None,
    source: str = "zoom",
) -> dict[str, Any]:
    """File a meeting transcript under Work/Meetings/ and backlink from today's daily note."""
    d = recorded_at or date.today()
    filename = f"{d.isoformat()} - {title}.md"
    rel_path = f"{load_config().vault.meetings_dir}/{filename}"
    from sophonic.skills import template as _template
    note_content = _template(
        "obsidian", "meeting",
        source=source,
        recorded_at=d.isoformat(),
        title=title,
        content=content,
    )
    write_note(rel_path, note_content)

    # Backlink in today's daily note
    backlink = f"- [[{rel_path.removesuffix('.md')}]]"
    daily = ensure_daily_note()
    daily_text = daily.read_text(encoding="utf-8")
    if backlink not in daily_text:
        if "## Notes" in daily_text:
            daily_text = daily_text.replace("## Notes\n", f"## Notes\n{backlink}\n", 1)
            daily.write_text(daily_text, encoding="utf-8")

    return {"saved": rel_path, "backlinked_in": str(daily.name)}


def load_config():
    from sophonic.config import load_config as _load
    return _load()


# ── Tool registry exported to __init__.py ─────────────────────────────────────

TOOLS: dict[str, Any] = {
    "obsidian_add_task": add_task,
    "obsidian_list_tasks": list_tasks,
    "obsidian_incomplete_yesterday": incomplete_yesterday,
    "obsidian_rollover": roll_over,
    "obsidian_complete_task": complete_task,
    "obsidian_daily_note": get_daily_note,
    "obsidian_build_daily_note": build_daily_note,
    "obsidian_upsert_section": upsert_section,
    "obsidian_read_note": read_note,
    "obsidian_write_note": write_note,
    "obsidian_append_note": append_note,
    "obsidian_search": search_vault,
    "obsidian_save_meeting_note": save_meeting_note,
}
