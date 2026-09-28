"""Tests for the shared action-item extractor's date-aware helpers.

`_extract_action_items` (plain, undated) is exercised via `tests/test_zoom.py`'s
existing suite through the `sophonic.zoom` re-export — not duplicated here. This file
covers the date-tracking additions used only by the Google Docs path
(`sophonic.gdrive.list_doc_action_items`): recognizing a recurring meeting's date
marker, splitting a rolling multi-meeting doc into per-meeting chunks at those markers,
and tagging each extracted item with its chunk's date.
"""

from __future__ import annotations

from datetime import date


def test_line_date_recognizes_bare_slash_date():
    from sophonic.action_items import _line_date

    assert _line_date("9/25/2026") == date(2026, 9, 25)


def test_line_date_recognizes_leading_written_date_with_trailing_text():
    from sophonic.action_items import _line_date

    assert _line_date("Sep 25, 2026 | Lakehouse L1: Data Architecture Sync") == date(2026, 9, 25)


def test_line_date_recognizes_leading_iso_date():
    from sophonic.action_items import _line_date

    assert _line_date("2026-09-25 meeting notes") == date(2026, 9, 25)


def test_line_date_returns_none_for_non_date_lines():
    from sophonic.action_items import _line_date

    assert _line_date("") is None
    assert _line_date("Action items") is None
    assert _line_date("The team agreed to move forward with the plan.") is None


def test_split_into_dated_chunks_with_no_markers_is_one_undated_chunk():
    from sophonic.action_items import _split_into_dated_chunks

    text = "Action items\n* Do the thing\n"
    assert _split_into_dated_chunks(text) == [(None, text.rstrip("\n"))]


def test_split_into_dated_chunks_splits_at_each_marker():
    from sophonic.action_items import _split_into_dated_chunks

    text = (
        "9/25/2026\n"
        "Action items\n"
        "* Recent item\n"
        "9/18/2026\n"
        "Action items\n"
        "* Old item\n"
    )
    chunks = _split_into_dated_chunks(text)
    assert [d for d, _ in chunks] == [date(2026, 9, 25), date(2026, 9, 18)]
    assert "Recent item" in chunks[0][1]
    assert "Old item" not in chunks[0][1]
    assert "Old item" in chunks[1][1]


def test_extract_dated_action_items_tags_each_item_with_its_section_date():
    from sophonic.action_items import _extract_dated_action_items

    text = (
        "9/25/2026\n"
        "Action items\n"
        "* Jamie Rivera to ship the report\n"
        "9/18/2026\n"
        "Action items\n"
        "* Jamie Rivera to file the old thing\n"
    )
    result = _extract_dated_action_items(text)
    assert result == [
        (date(2026, 9, 25), "Jamie Rivera to ship the report"),
        (date(2026, 9, 18), "Jamie Rivera to file the old thing"),
    ]


def test_extract_dated_action_items_untagged_when_no_marker_present():
    from sophonic.action_items import _extract_dated_action_items

    text = "Action items\n* Jamie Rivera to ship the report\n"
    assert _extract_dated_action_items(text) == [(None, "Jamie Rivera to ship the report")]


def test_extract_dated_action_items_confines_extraction_past_headings_the_stop_list_misses():
    """Regression guard for the real bug: a rolling doc whose intervening headings
    ("PSAs", "Meeting notes") aren't in the shared parser's small stop-word vocabulary,
    so `_extract_action_items` alone would keep scanning bullets straight through into
    the NEXT (older) meeting's own Action-items section. Chunking at date markers
    before extraction must confine each meeting's items to its own chunk regardless."""
    from sophonic.action_items import _extract_dated_action_items

    text = (
        "9/25/2026\n"
        "Action items\n"
        "* Jamie Rivera to ship the report\n"
        "PSAs\n"
        "* Some announcement bullet\n"
        "Meeting notes\n"
        "* A discussion bullet, not a task\n"
        "9/18/2026\n"
        "Action items\n"
        "* Jamie Rivera to file the old thing\n"
    )
    result = _extract_dated_action_items(text)
    recent_items = [item for d, item in result if d == date(2026, 9, 25)]
    old_items = [item for d, item in result if d == date(2026, 9, 18)]
    assert "Jamie Rivera to file the old thing" not in recent_items
    assert old_items == ["Jamie Rivera to file the old thing"]
