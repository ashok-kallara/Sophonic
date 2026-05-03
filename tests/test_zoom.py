"""Tests for Zoom scraper (mocked Playwright) and transcript filing."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time


def _ctx_with_page(page):
    ctx = AsyncMock()
    ctx.new_page = AsyncMock(return_value=page)
    return ctx


def _mock_recording_list_page(url="https://zoom.us/recording"):
    page = AsyncMock()
    page.url = url
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()

    # Two recording rows
    def _make_row(title, date_str, link):
        row = AsyncMock()

        async def _qs(sel):
            if any(k in sel for k in ("name", "topic", "first-child", "cell:first")):
                el = AsyncMock()
                el.inner_text = AsyncMock(return_value=title)
                el.get_attribute = AsyncMock(return_value=None)
                return el
            if any(k in sel for k in ("time", "date", "start-time")):
                el = AsyncMock()
                el.get_attribute = AsyncMock(return_value=date_str)
                el.inner_text = AsyncMock(return_value=date_str)
                return el
            if "a[href" in sel:
                el = AsyncMock()
                el.get_attribute = AsyncMock(return_value=link)
                return el
            return None

        row.query_selector = AsyncMock(side_effect=_qs)
        return row

    rows = [
        _make_row("Weekly Standup", "2026-05-03", "/recording/abc"),
        _make_row("Design Review", "2026-04-28", "/recording/def"),
    ]
    page.query_selector_all = AsyncMock(return_value=rows)
    return page


def _mock_transcript_page(transcript_text="Speaker 1: Hello"):
    page = AsyncMock()
    page.url = "https://zoom.us/recording/abc"
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    async def _qs(sel):
        # Body selector matched first — it contains "transcript" but also has "pre"
        if "pre" in sel or "vtt-transcript" in sel or "transcript-content" in sel:
            el = AsyncMock()
            el.inner_text = AsyncMock(return_value=transcript_text)
            return el
        # Tab selector is narrower (role="tab" or data-testid="transcript-tab")
        if "tab" in sel.lower() and "role" in sel.lower():
            tab = AsyncMock()
            tab.click = AsyncMock()
            return tab
        if any(k in sel for k in ("h1", "title")):
            el = AsyncMock()
            el.inner_text = AsyncMock(return_value="Weekly Standup")
            return el
        return None

    page.query_selector = AsyncMock(side_effect=_qs)
    return page


@pytest.mark.asyncio
async def test_list_recordings_returns_entries():
    from akashic.tools.zoom import _list_recordings_async

    page = _mock_recording_list_page()
    with patch("akashic.browser.persistent_browser") as mock_pb:
        mock_pb.return_value.__aenter__ = AsyncMock(return_value=_ctx_with_page(page))
        mock_pb.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _list_recordings_async("https://zoom.us/recording", since_days=30)

    assert isinstance(result, list)
    assert len(result) >= 1
    assert any(r.get("title") == "Weekly Standup" for r in result)


@pytest.mark.asyncio
async def test_list_recordings_needs_auth():
    from akashic.tools.zoom import _list_recordings_async

    page = _mock_recording_list_page(url="https://zoom.us/signin")
    with patch("akashic.browser.persistent_browser") as mock_pb:
        mock_pb.return_value.__aenter__ = AsyncMock(return_value=_ctx_with_page(page))
        mock_pb.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _list_recordings_async("https://zoom.us/recording", since_days=7)

    assert result == [{"needs_auth": True, "run": "akashic auth zoom"}]


@pytest.mark.asyncio
async def test_fetch_transcript_extracts_text():
    from akashic.tools.zoom import _fetch_transcript_async

    page = _mock_transcript_page("Speaker 1: Hello\nSpeaker 2: Hi there")
    with patch("akashic.browser.persistent_browser") as mock_pb:
        mock_pb.return_value.__aenter__ = AsyncMock(return_value=_ctx_with_page(page))
        mock_pb.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _fetch_transcript_async("https://zoom.us/recording/abc")

    assert "Speaker 1: Hello" in result["transcript_text"]


@freeze_time("2026-05-03")
def test_save_transcript_files_meeting_note(use_fixture_vault):
    from akashic.tools.zoom import save_transcript

    with patch("akashic.tools.zoom.transcript") as mock_t:
        mock_t.return_value = {
            "url": "https://zoom.us/recording/xyz",
            "title": "Q2 Planning",
            "transcript_text": "Alice: Let's discuss Q2\nBob: Sounds good",
        }
        result = save_transcript(
            "https://zoom.us/recording/xyz",
            title="Q2 Planning",
            recorded_date="2026-05-03",
        )

    assert "saved" in result
    assert "Q2 Planning" in result["saved"]
    note_path = use_fixture_vault / result["saved"]
    assert note_path.exists()
    content = note_path.read_text()
    assert "zoom" in content
    assert "Alice: Let's discuss Q2" in content

    daily = use_fixture_vault / "Daily" / "DAILY-2026-05-03.md"
    if daily.exists():
        assert "Q2 Planning" in daily.read_text()


def test_parse_recording_date_formats():
    from akashic.tools.zoom import _parse_recording_date

    assert _parse_recording_date("2026-05-03") == date(2026, 5, 3)
    assert _parse_recording_date("2026-05-03T09:00:00Z") == date(2026, 5, 3)
    assert _parse_recording_date("") is None
