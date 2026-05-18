"""Zoom transcript scraper — web-only via Playwright.

Navigates zoom.us/recording, lists recordings, fetches transcripts,
and optionally files them as Obsidian meeting notes.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sophonic.browser import run_async

_NEEDS_AUTH = {"needs_auth": True, "run": "sophonic auth zoom"}

_SELECTORS = {
    # Recording list page
    "recording_row": (
        "tr[data-recordingid], "
        ".recording-list__item, "
        "[data-testid='recording-item'], "
        ".zm-table-row"
    ),
    "recording_title": (
        ".recording-name, "
        "[data-testid='recording-topic'], "
        "td:first-child a, "
        ".zm-table-cell:first-child"
    ),
    "recording_date": (
        "time, "
        ".recording-date, "
        "[data-testid='recording-start-time']"
    ),
    "recording_link": "a[href*='/recording/'], a[href*='/rec/']",
    # Recording detail page
    "transcript_tab": (
        '[data-testid="transcript-tab"], '
        'a:has-text("Transcript"), '
        'button:has-text("Transcript"), '
        '[role="tab"]:has-text("Transcript")'
    ),
    "transcript_body": (
        ".transcript-content, "
        ".vtt-transcript, "
        "[data-testid='transcript-content'], "
        "pre"
    ),
}


def _parse_recording_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%b %d, %Y", "%m/%d/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(raw[:len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    return None


async def _list_recordings_async(recordings_url: str, since_days: int) -> list[dict[str, Any]]:
    from sophonic.browser import persistent_browser

    async with persistent_browser("zoom") as ctx:
        page = await ctx.new_page()
        await page.goto(recordings_url, timeout=30_000)
        await page.wait_for_load_state("networkidle", timeout=15_000)

        if any(k in page.url for k in ("signin", "login", "sso")):
            return [_NEEDS_AUTH]

        cutoff = date.today() - timedelta(days=since_days)
        rows = await page.query_selector_all(_SELECTORS["recording_row"])
        results = []

        for row in rows[:50]:
            title_el = await row.query_selector(_SELECTORS["recording_title"])
            date_el = await row.query_selector(_SELECTORS["recording_date"])
            link_el = await row.query_selector(_SELECTORS["recording_link"])

            title = (await title_el.inner_text()).strip() if title_el else "Unknown"
            date_raw = ""
            if date_el:
                date_raw = await date_el.get_attribute("datetime") or await date_el.inner_text()
            link = await link_el.get_attribute("href") if link_el else ""

            rec_date = _parse_recording_date(date_raw)
            if rec_date and rec_date < cutoff:
                continue

            results.append({
                "title": title,
                "date": date_raw.strip(),
                "link": link,
                "has_transcript": None,  # resolved lazily
            })

        return results or [{"message": "No recordings found — try increasing since_days"}]


async def _fetch_transcript_async(recording_url: str) -> dict[str, Any]:
    """Navigate to a recording detail page and extract the transcript text."""
    from sophonic.browser import persistent_browser

    async with persistent_browser("zoom") as ctx:
        page = await ctx.new_page()
        if not recording_url.startswith("http"):
            recording_url = f"https://zoom.us{recording_url}"
        await page.goto(recording_url, timeout=30_000)
        await page.wait_for_load_state("networkidle", timeout=15_000)

        if any(k in page.url for k in ("signin", "login", "sso")):
            return _NEEDS_AUTH

        # Try to click the Transcript tab if present
        tab = await page.query_selector(_SELECTORS["transcript_tab"])
        if tab:
            await tab.click()
            await page.wait_for_timeout(2000)

        body_el = await page.query_selector(_SELECTORS["transcript_body"])
        transcript_text = (await body_el.inner_text()).strip() if body_el else ""

        # Derive title from page title or h1
        title_el = await page.query_selector("h1, title")
        title = (await title_el.inner_text()).strip() if title_el else "Meeting"

        return {
            "url": recording_url,
            "title": title,
            "transcript_text": transcript_text,
        }


def transcripts(since_days: int = 7) -> list[dict[str, Any]]:
    """List recent Zoom recordings from the web portal."""
    from sophonic.config import load_config
    url = load_config().zoom.recordings_url
    return run_async(_list_recordings_async(url, since_days))


def transcript(recording_url: str) -> dict[str, Any]:
    """Fetch the transcript text for a specific Zoom recording URL."""
    return run_async(_fetch_transcript_async(recording_url))


def save_transcript(
    recording_url: str,
    title: str | None = None,
    recorded_date: str | None = None,
) -> dict[str, Any]:
    """Fetch a Zoom transcript and save it as an Obsidian meeting note.

    Returns the path of the saved note and a backlink confirmation.
    The day's daily note gets a backlink under ## Notes.
    """
    from sophonic.tools.obsidian import save_meeting_note

    data = transcript(recording_url)
    if "needs_auth" in data:
        return data
    if "error" in data:
        return data

    note_title = title or data.get("title", "Meeting")
    note_date: date | None = None
    if recorded_date:
        note_date = _parse_recording_date(recorded_date)

    transcript_text = data.get("transcript_text", "")
    result = save_meeting_note(
        title=note_title,
        content=f"**Source URL:** {recording_url}\n\n```\n{transcript_text}\n```",
        recorded_at=note_date,
        source="zoom",
    )
    return result


TOOLS: dict[str, Any] = {
    "zoom_transcripts": transcripts,
    "zoom_transcript": transcript,
    "zoom_save_transcript": save_transcript,
}
