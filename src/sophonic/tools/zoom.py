"""Zoom AI meeting notes — read the signed-in web session's AI Companion notes.

Zoom auto-generates a "Note" (AI Companion) for each meeting, stored in Zoom Docs.
This lists those notes and fetches their content by driving the authenticated Zoom
web session (seeded from your pasted ZOOM_COOKIES) — no browser login, no cloud
recording required. Content is read from the rendered Zoom Docs page.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import date
from typing import Any

from sophonic.browser import run_async

_NEEDS_AUTH = {
    "needs_auth": True,
    "run": "sophonic config set-secret ZOOM_COOKIES --stdin",
    "detail": "Log in to zoom.us in your browser, copy the session cookies, and paste them.",
}

_NOTES_URL = "https://zoom.us/notes"
_DOC_URL = "https://docs.zoom.us/doc/{doc_id}"
# meeting notes are titled like "Weekly Sync 2026-07-31 13:33(GMT-4:00)"
_TITLE_DATE_RE = re.compile(r"\s*(\d{4}-\d{2}-\d{2})[ T]\d{1,2}:\d{2}")
# Zoom Docs editor content containers, most specific first
_CONTENT_SELECTORS = [
    "[contenteditable='true']",
    "div[role='textbox']",
    "main",
    "article",
]
# Zoom Docs UI chrome (toolbar + tab labels) to drop from the scraped note text
_CHROME_LINES = {
    "Add to starred", "Share", "Copy doc link", "View Docs activity center",
    "More options", "Add icon", "Page options", "Manual notes", "Transcript",
}


def _clean_note_text(text: str) -> str:
    """Drop Zoom Docs toolbar/tab chrome lines from scraped note text."""
    lines = [ln for ln in text.splitlines() if ln.strip() not in _CHROME_LINES]
    out: list[str] = []
    for ln in lines:
        # collapse consecutive blank lines
        if not ln.strip() and out and not out[-1].strip():
            continue
        # drop a line identical to the previous kept line (e.g. duplicated title)
        if out and ln.strip() and ln.strip() == out[-1].strip():
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _parse_cookies(raw: str) -> list[dict[str, Any]]:
    """Parse a 'name=value; name2=value2' cookie header into Playwright cookie dicts."""
    cookies: list[dict[str, Any]] = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".zoom.us",
            "path": "/",
            "secure": True,
        })
    return cookies


def _zoom_cookies() -> list[dict[str, Any]]:
    """Session cookies pasted by the user via `sophonic config set-secret ZOOM_COOKIES`."""
    return _parse_cookies(os.environ.get("ZOOM_COOKIES", ""))


def _is_login(url: str) -> bool:
    return any(k in url.lower() for k in ("signin", "login", "sso"))


def _split_title(title: str) -> tuple[str, str | None]:
    """Split a note title into (meeting_name, iso_date) using the embedded timestamp."""
    match = _TITLE_DATE_RE.search(title)
    if match:
        return title[: match.start()].strip(), match.group(1)
    return title, None


# ── list notes ───────────────────────────────────────────────────────────────

async def _list_notes_async(cookies: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    from sophonic.browser import persistent_browser

    captured: dict[str, Any] = {}
    async with persistent_browser("zoom", cookies=cookies) as ctx:
        page = await ctx.new_page()

        async def _grab(resp):
            if "api/search/file" in resp.url and "items" not in captured:
                try:
                    captured["items"] = (await resp.json()).get("items", [])
                except Exception:
                    pass

        page.on("response", lambda r: asyncio.create_task(_grab(r)))
        try:
            await page.goto(_NOTES_URL, wait_until="domcontentloaded", timeout=45_000)
        except Exception:
            pass
        for _ in range(30):  # wait up to ~15s for the notes list to load
            if "items" in captured:
                break
            await page.wait_for_timeout(500)
        if "items" not in captured:
            return [_NEEDS_AUTH] if _is_login(page.url) else [{"message": "No Zoom notes found"}]
        items = captured["items"]

    notes: list[dict[str, Any]] = []
    for item in items[:limit]:
        f = item.get("file", item)
        title = f.get("title") or "Untitled"
        meeting, iso = _split_title(title)
        notes.append({
            "id": f.get("id"),
            "title": title,
            "meeting": meeting,
            "date": iso,
            "link": f.get("fileLink"),
            "is_meeting_note": bool(f.get("meetingNotes")),
        })
    return notes or [{"message": "No Zoom notes found"}]


# ── fetch note content ─────────────────────────────────────────────────────────

async def _fetch_note_async(cookies: list[dict[str, Any]], doc_id: str) -> dict[str, Any]:
    from sophonic.browser import persistent_browser

    async with persistent_browser("zoom", cookies=cookies) as ctx:
        page = await ctx.new_page()
        await page.goto(_DOC_URL.format(doc_id=doc_id), wait_until="domcontentloaded", timeout=45_000)
        if _is_login(page.url):
            return _NEEDS_AUTH
        # let the collaborative doc render
        await page.wait_for_timeout(6_000)

        title = ""
        try:
            title = (await page.title()).strip()
        except Exception:
            pass

        # prefer the most specific content region that has real text (the doc body,
        # which excludes the surrounding toolbar), falling back to <body>
        best = ""
        for sel in _CONTENT_SELECTORS:
            parts = []
            for el in await page.query_selector_all(sel):
                try:
                    parts.append(await el.inner_text())
                except Exception:
                    continue
            joined = "\n".join(p for p in parts if p).strip()
            if len(joined) >= 200:
                best = joined
                break
        if not best:
            best = await page.inner_text("body")

        return {"id": doc_id, "title": title, "text": _clean_note_text(best)}


# ── public tools ─────────────────────────────────────────────────────────────

def notes(limit: int = 20) -> list[dict[str, Any]]:
    """List recent Zoom AI meeting notes (title, meeting, date, id, link)."""
    cookies = _zoom_cookies()
    if not cookies:
        return [_NEEDS_AUTH]
    return run_async(_list_notes_async(cookies, limit))


def note(doc_id: str) -> dict[str, Any]:
    """Fetch the content of a Zoom AI meeting note by its doc id."""
    cookies = _zoom_cookies()
    if not cookies:
        return _NEEDS_AUTH
    return run_async(_fetch_note_async(cookies, doc_id))


def save_note(doc_id: str, title: str | None = None) -> dict[str, Any]:
    """Fetch a Zoom AI meeting note and save it as an Obsidian meeting note.

    Files the note under the meetings directory and backlinks it in the daily note.
    """
    from sophonic.tools.obsidian import save_meeting_note

    data = note(doc_id)
    if "needs_auth" in data or "error" in data:
        return data

    raw_title = title or data.get("title") or "Zoom Meeting"
    meeting, iso = _split_title(raw_title)
    recorded_at: date | None = None
    if iso:
        try:
            recorded_at = date.fromisoformat(iso)
        except ValueError:
            recorded_at = None

    return save_meeting_note(
        title=meeting or raw_title,
        content=f"**Source:** Zoom AI note ({_DOC_URL.format(doc_id=doc_id)})\n\n{data.get('text', '')}",
        recorded_at=recorded_at,
        source="zoom",
    )


# ── action items → tasks ────────────────────────────────────────────────────────

# Headings that begin an action-item section (collection continues across adjacent ones).
_ACTION_HEADING_RE = re.compile(
    r"^\s*(action items?|next steps?|follow[\s-]?ups?|to-?dos?)\s*:?\s*$", re.I
)
# Non-action section headings that end collection.
_STOP_HEADINGS = {
    "quick recap", "recap", "summary", "key outcomes", "outcomes", "overview",
    "details", "notes", "transcript", "manual notes", "attendees", "recording",
    "decisions", "discussion",
}
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")


def _extract_action_items(text: str) -> list[str]:
    """Pull the action-item lines out of a scraped Zoom AI note.

    Collects list items under an "Action Items"/"Next Steps"/"Follow-ups" heading
    until the next non-action section heading.
    """
    items: list[str] = []
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if _ACTION_HEADING_RE.match(line):
            in_section = True
            continue
        if not in_section or not line:
            continue
        norm = line.lower().rstrip(":").strip()
        if line.startswith("#") or norm in _STOP_HEADINGS:
            break
        m = _BULLET_RE.match(raw)
        item = (m.group(1) if m else line).strip()
        item = re.sub(r"^\[[ xX]\]\s*", "", item).strip()  # drop any checkbox marker
        if item:
            items.append(item)
    return items


def _resolve_range(on, since, until, days, ref: date) -> tuple[date, date]:
    """Resolve a (start, end) date window from the supported selectors.

    Precedence: on → days → since/until → default (today). Values may be ISO dates
    or natural language ("yesterday", "last Monday").
    """
    from datetime import timedelta

    from sophonic.dates import parse_date

    def _p(value: str) -> date:
        d = parse_date(value)
        if d is None:
            raise ValueError(f"Could not parse date: {value!r}")
        return d

    if on:
        d = _p(on)
        return d, d
    if days:
        if days < 1:
            raise ValueError("days must be >= 1")
        return ref - timedelta(days=days - 1), ref
    if since or until:
        return (_p(since) if since else ref), (_p(until) if until else ref)
    return ref, ref


def _meeting_ref(n: dict[str, Any]) -> str:
    """A traceable reference to the source meeting for a task line.

    Prefers a clickable markdown link to the Zoom note; falls back to plain text.
    """
    meeting = n.get("meeting") or "Zoom meeting"
    iso = n.get("date")
    label = f"{meeting} — {iso}" if iso else meeting
    link = n.get("link")
    return f"[{label}]({link})" if link else f"({label})"


def action_items(
    on: str | None = None,
    since: str | None = None,
    until: str | None = None,
    days: int | None = None,
    owner: str | None = None,
    dry_run: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """Pull action items from Zoom meeting notes and add them to today's tasks.

    Defaults to today's meetings. Widen the window with `on`/`since`/`until` (ISO or
    natural language) or `days` (last N days including today). `owner` keeps only items
    whose text contains that substring (e.g. your name). `dry_run` previews without
    writing. Re-runs are deduped against today's note, so it's safe to run repeatedly.
    """
    cookies = _zoom_cookies()
    if not cookies:
        return _NEEDS_AUTH

    try:
        start, end = _resolve_range(on, since, until, days, date.today())
    except ValueError as exc:
        return {"error": str(exc)}

    listing = notes(limit)
    if listing and isinstance(listing[0], dict) and ("needs_auth" in listing[0] or "message" in listing[0]):
        return listing[0]

    selected = []
    for n in listing:
        iso = n.get("date")
        if not iso:
            continue
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            continue
        if start <= d <= end:
            selected.append(n)

    from sophonic.tools.obsidian import add_task, get_daily_note

    existing = get_daily_note()  # today's note — dedupe target for re-runs
    seen: set[str] = set()
    collected: list[dict[str, Any]] = []

    for n in selected:
        data = note(n["id"])
        if not isinstance(data, dict) or "text" not in data:
            continue
        ref = _meeting_ref(n)
        for item in _extract_action_items(data["text"]):
            if owner and owner.lower() not in item.lower():
                continue
            key = item.lower()
            if key in seen or item in existing:
                continue
            seen.add(key)
            # Stamp the source meeting into the task line so it's traceable.
            entry = {"item": item, "meeting": n.get("meeting"), "date": n.get("date"), "ref": ref}
            if not dry_run:
                add_task(text=f"{item} {ref}", tags=["zoom"])
            collected.append(entry)

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "meetings_scanned": len(selected),
        "action_items": collected,
        "count": len(collected),
        "dry_run": dry_run,
    }


TOOLS: dict[str, Any] = {
    "zoom_notes": notes,
    "zoom_note": note,
    "zoom_save_note": save_note,
    "zoom_action_items": action_items,
}
