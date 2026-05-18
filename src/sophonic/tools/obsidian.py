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

_DAILY_TEMPLATE = """\
# {title}
#sophonic

## Tasks

## Notes

"""


# ── Daily note helpers ────────────────────────────────────────────────────────

def ensure_daily_note(for_date: date | None = None) -> Path:
    """Return path to the daily note, creating it from template if missing."""
    path = daily_note_path(for_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        d = for_date or date.today()
        title = f"DAILY {d.isoformat()}"
        path.write_text(_DAILY_TEMPLATE.format(title=title), encoding="utf-8")
    return path


def get_daily_note(for_date: date | None = None) -> str:
    """Return the full text of a daily note (creates it if missing)."""
    return ensure_daily_note(for_date).read_text(encoding="utf-8")


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


def roll_over(
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    """Copy incomplete tasks from from_date's note into to_date's note. Idempotent."""
    from sophonic.dates import today, yesterday

    src_date = from_date or yesterday()
    dst_date = to_date or today()

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
    from sophonic.config import load_config as _cfg
    frontmatter = f"---\nsource: {source}\nrecorded_at: {d.isoformat()}\ntags: [sophonic]\n---\n\n"
    write_note(rel_path, frontmatter + f"# {title}\n\n" + content)

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
    "obsidian_read_note": read_note,
    "obsidian_write_note": write_note,
    "obsidian_append_note": append_note,
    "obsidian_search": search_vault,
    "obsidian_save_meeting_note": save_meeting_note,
}
