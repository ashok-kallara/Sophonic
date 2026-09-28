"""Shared plain-text "action item" extractor.

Pulls itemized action-item lines out of scraped/exported note text — originally built
for Zoom AI Companion notes (see `sophonic/zoom.py`) and reused as-is for Google Docs
plain-text exports (see `sophonic/gdrive.py`), since both are heading + bullet-list
text with the same rendering quirks to work around.
"""

from __future__ import annotations

import re
from datetime import date

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
# Some sources sometimes render a bullet glyph as its own line, with the item's text
# starting on the next line(s) — this matches such a marker-only line.
_BULLET_MARKER_ONLY_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*$")
# Zero-width/invisible marks some sources sprinkle into note text (format joiners, BOM).
_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\ufeff\u2060]")
# AI Companion citation badges (e.g. a "\ufeff16\u200b\ufeff17" run): a "\ufeff<digits>"
# marker per citation, optionally chained with a zero-width joiner — meaningless as
# plain text once scraped, so strip the whole run rather than leaving digits smushed
# together with no separator.
_CITATION_RUN_RE = re.compile("\\s*(?:\ufeff\\d+\u200b?)+")


def _merge_split_bullets(lines: list[str]) -> list[str]:
    """Rejoin a bullet marker rendered on its own line with the item text that
    follows it on the next line(s), so the bullet regex below can see marker and
    text together instead of two separate, individually non-matching lines."""
    merged: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        if _BULLET_MARKER_ONLY_RE.match(lines[i]):
            marker = lines[i].strip()
            i += 1
            text_parts = []
            while i < n and lines[i].strip():
                text_parts.append(lines[i].strip())
                i += 1
            merged.append(f"{marker} {' '.join(text_parts)}".strip())
            continue
        merged.append(lines[i])
        i += 1
    return merged


def _extract_action_items(text: str) -> list[str]:
    """Pull the action-item lines out of scraped/exported note text.

    Collects list items under an "Action Items"/"Next Steps"/"Follow-ups" heading
    until the next non-action section heading. Handles two rendering quirks seen in
    both Zoom Docs and Google Docs exports: a bullet marker split onto its own line
    (rejoined via `_merge_split_bullets` before scanning), and a leading table-of-contents
    block that repeats the same heading names with no blank-line separation — a heading
    only opens the section if it's preceded by a blank line (or starts the document),
    which a real "Action Items" heading always is but a ToC entry never is.
    """
    lines = _merge_split_bullets(text.splitlines())

    items: list[str] = []
    in_section = False
    for i, raw in enumerate(lines):
        # `stripped` keeps citation markers intact for the bullet match below;
        # `heading_line` is only for heading/stop-heading comparison.
        stripped = raw.strip()
        heading_line = _ZERO_WIDTH_RE.sub("", stripped)
        if _ACTION_HEADING_RE.match(heading_line):
            preceded_by_blank = i == 0 or not lines[i - 1].strip()
            if in_section or preceded_by_blank:
                in_section = True
            continue
        if not in_section or not stripped:
            continue
        norm = heading_line.lower().rstrip(":").strip()
        if heading_line.startswith("#") or norm in _STOP_HEADINGS:
            break
        m = _BULLET_RE.match(stripped)
        if not m:
            continue  # only itemized entries become tasks — skip narrative/summary prose
        item = re.sub(r"^\[[ xX]\]\s*", "", m.group(1)).strip()  # drop any checkbox marker
        item = _CITATION_RUN_RE.sub("", item)
        item = _ZERO_WIDTH_RE.sub("", item).strip()
        if item:
            items.append(item)
    return items


# ── dated variant (rolling multi-meeting docs) ───────────────────────────────
# A single Google Doc is sometimes reused across many recurring meetings (one running
# "Agenda" doc, a new dated section prepended every week) rather than one doc per
# meeting the way Zoom notes are. `_extract_action_items` above has no concept of
# section boundaries beyond a small Zoom-specific stop-heading vocabulary — pointed at
# a doc using different heading names (e.g. "PSAs", "Meeting notes"), it will keep
# scanning bullets straight through into a much older meeting's own Action-items
# section. The functions below split such a doc into per-meeting chunks at its own
# recurring date markers *before* handing each chunk to the untouched extractor above,
# so a caller (sophonic.gdrive) can filter out items from meetings that are already
# long since handled.

# A line that is *entirely* a date, e.g. "9/25/2026" — the marker many rolling
# agenda docs prepend to each new week's section.
_BARE_SLASH_DATE_RE = re.compile(r"^\s*(\d{1,2}/\d{1,2}/\d{4})\s*$")
# A line that *starts* with a written month-name date, possibly followed by more text
# after a separator, e.g. "Sep 25, 2026 | Lakehouse L1: Data Architecture Sync".
_LEADING_WRITTEN_DATE_RE = re.compile(r"^\s*([A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})\b")
# A line that starts with an ISO date, e.g. "2026-09-25 meeting notes".
_LEADING_ISO_DATE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\b")
_DATE_LINE_PATTERNS = (_BARE_SLASH_DATE_RE, _LEADING_WRITTEN_DATE_RE, _LEADING_ISO_DATE_RE)


def _line_date(line: str) -> date | None:
    """The date this line marks the start of a new meeting's section with, or None.

    A regex prefilter picks candidate lines; the matched substring still has to parse
    as a real date via `sophonic.dates.parse_date` (which resolves month names etc.) —
    this rejects date-shaped-but-nonsensical text (e.g. "Version 2 2026") that the
    regex alone can't distinguish from a real date heading.
    """
    stripped = line.strip()
    if not stripped:
        return None
    for pattern in _DATE_LINE_PATTERNS:
        m = pattern.match(stripped)
        if m:
            from sophonic.dates import parse_date

            return parse_date(m.group(1))
    return None


def _split_into_dated_chunks(text: str) -> list[tuple[date | None, str]]:
    """Split doc text into (date, chunk_text) pairs at each recognized date marker.

    A doc with no recognizable date markers at all (the common case — a normal Doc,
    or Zoom note text, neither of which use this rolling-meeting convention) comes
    back as a single `(None, ...)` chunk covering the whole text. Any content before
    the first marker (rare — an undated preamble) is its own leading `(None, ...)`
    chunk rather than being dropped.
    """
    lines = text.splitlines()
    markers: list[tuple[int, date]] = []
    for i, line in enumerate(lines):
        d = _line_date(line)
        if d is not None:
            markers.append((i, d))

    if not markers:
        return [(None, "\n".join(lines))]

    chunks: list[tuple[date | None, str]] = []
    if markers[0][0] > 0:
        chunks.append((None, "\n".join(lines[: markers[0][0]])))
    for idx, (start, marker_date) in enumerate(markers):
        end = markers[idx + 1][0] if idx + 1 < len(markers) else len(lines)
        # Skip the marker line itself: it's a boundary signal, not chunk content, and
        # leaving it in would sit directly before an "Action items" heading with no
        # blank line between them — tripping _extract_action_items' own guard against
        # opening a section for a heading that isn't preceded by a blank line (the
        # guard that keeps a table-of-contents entry from being mistaken for a real
        # heading), so the section would never open for any chunk after the first.
        chunks.append((marker_date, "\n".join(lines[start + 1 : end])))
    return chunks


def _extract_dated_action_items(text: str) -> list[tuple[date | None, str]]:
    """Like `_extract_action_items`, but tags each item with its meeting's date.

    Splits into per-meeting chunks first (see `_split_into_dated_chunks`) so each
    extraction pass is confined to one meeting's text, then runs the ordinary
    extractor on each chunk. An item from a chunk with no detected date marker comes
    back tagged `None` — unknown, not "recent" or "stale"; callers should keep
    unknown-dated items by default rather than treat the absence of a date as staleness.
    """
    return [
        (chunk_date, item)
        for chunk_date, chunk_text in _split_into_dated_chunks(text)
        for item in _extract_action_items(chunk_text)
    ]
