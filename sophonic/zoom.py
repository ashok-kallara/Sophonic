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

import httpx

from sophonic.browser import run_async

_NEEDS_AUTH = {
    "needs_auth": True,
    "run": "uv run python scripts/config.py set-secret ZOOM_COOKIES --stdin",
    "detail": (
        "Zoom web session cookies are missing/expired. In your browser, open DevTools "
        "→ Network, click any request to zoom.us, and copy the whole 'Cookie:' request "
        "header value; paste it into "
        "`uv run python scripts/config.py set-secret ZOOM_COOKIES --stdin`."
    ),
}

_NOTES_URL = "https://zoom.us/notes"
# A gated page: an authenticated session returns 200; an expired/missing one 302s to /signin.
_AUTH_PROBE_URL = "https://zoom.us/profile"
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
    """Parse a Cookie request header into Playwright cookie dicts.

    Accepts the raw `Cookie:` request-header value copied from browser DevTools —
    either the bare `name=value; name2=value2` string or the whole line including a
    leading `Cookie:` label (which is stripped).
    """
    raw = raw.strip()
    if raw[:7].lower() == "cookie:":  # tolerate a pasted "Cookie: …" header line
        raw = raw[7:].strip()
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

def check_auth() -> dict[str, Any]:
    """Lightweight validity probe for the Zoom web session — no browser.

    Requests a gated page with the pasted cookies: a live session returns 200; an
    expired or missing session 302-redirects to sign-in. Returns {ok, detail}.
    """
    cookies = _zoom_cookies()
    if not cookies:
        return {"ok": False, "detail": "ZOOM_COOKIES not set"}
    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    try:
        resp = httpx.get(
            _AUTH_PROBE_URL,
            headers={"Cookie": cookie_header},
            follow_redirects=False,
            timeout=15,
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"probe request failed: {exc}"}

    if resp.status_code == 200:
        return {"ok": True, "detail": "Zoom web session valid"}
    if resp.is_redirect and _is_login(resp.headers.get("location", "")):
        return {"ok": False, "detail": "session expired — cookies redirect to sign-in"}
    return {"ok": False, "detail": f"unexpected response: HTTP {resp.status_code}"}


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


# ── action items ─────────────────────────────────────────────────────────────

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
        if not m:
            continue  # only itemized entries become tasks — skip narrative/summary prose
        item = re.sub(r"^\[[ xX]\]\s*", "", m.group(1)).strip()  # drop any checkbox marker
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


def action_items(
    on: str | None = None,
    since: str | None = None,
    until: str | None = None,
    days: int | None = None,
    owner: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Extract action items from Zoom meeting notes in a date window (read-only).

    Defaults to today's meetings. Widen the window with `on`/`since`/`until` (ISO or
    natural language) or `days` (last N days including today). `owner` keeps only items
    whose text contains that substring (e.g. your name).

    Returns every extracted item grouped by meeting; it does NOT touch the vault.
    The caller (the start-my-day/zoom skill) dedupes against today's note and writes the
    tasks, so this stays a pure fetcher.
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

    groups: list[dict[str, Any]] = []
    total = 0
    for n in selected:
        data = note(n["id"])
        if not isinstance(data, dict) or "text" not in data:
            continue
        items = [
            item
            for item in _extract_action_items(data["text"])
            if not owner or owner.lower() in item.lower()
        ]
        if not items:
            continue
        groups.append({
            "meeting": n.get("meeting"),
            "date": n.get("date"),
            "link": n.get("link"),
            "items": items,
        })
        total += len(items)

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "meetings_scanned": len(selected),
        "groups": groups,
        "count": total,
    }
