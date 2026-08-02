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


TOOLS: dict[str, Any] = {
    "zoom_notes": notes,
    "zoom_note": note,
    "zoom_save_note": save_note,
}
