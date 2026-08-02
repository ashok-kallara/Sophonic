"""Tests for the Zoom AI-notes tools (cookie parsing, title split, save)."""

from unittest.mock import patch

from freezegun import freeze_time


def test_parse_cookies_to_playwright_dicts():
    from sophonic.tools.zoom import _parse_cookies

    cookies = _parse_cookies("_zm_ssid=abc; zm_aid=def ; empty")
    names = {c["name"]: c["value"] for c in cookies}
    assert names == {"_zm_ssid": "abc", "zm_aid": "def"}
    assert all(c["domain"] == ".zoom.us" and c["path"] == "/" and c["secure"] for c in cookies)


def test_split_title_extracts_meeting_and_date():
    from sophonic.tools.zoom import _split_title

    meeting, iso = _split_title("Data Leads Weekly 2026-07-31 13:33(GMT-4:00)")
    assert meeting == "Data Leads Weekly"
    assert iso == "2026-07-31"

    meeting, iso = _split_title("Untitled note")
    assert meeting == "Untitled note"
    assert iso is None


def test_notes_needs_cookies(monkeypatch):
    from sophonic.tools import zoom

    monkeypatch.delenv("ZOOM_COOKIES", raising=False)
    result = zoom.notes()
    assert result[0]["needs_auth"] is True
    assert "ZOOM_COOKIES" in result[0]["run"]


def test_note_needs_cookies(monkeypatch):
    from sophonic.tools import zoom

    monkeypatch.delenv("ZOOM_COOKIES", raising=False)
    result = zoom.note("PUB4xyz")
    assert result["needs_auth"] is True


@freeze_time("2026-07-31")
def test_save_note_files_meeting_note(use_fixture_vault):
    from sophonic.tools import zoom

    with patch.object(zoom, "note") as mock_note:
        mock_note.return_value = {
            "id": "PUB4xyz",
            "title": "Data Leads Weekly 2026-07-31 13:33(GMT-4:00)",
            "text": "Key Outcomes\nThe team aligned on the offsite plan.\nAction Items\n- Ashok to follow up",
        }
        result = zoom.save_note("PUB4xyz")

    assert "saved" in result
    assert "Data Leads Weekly" in result["saved"]
    note_path = use_fixture_vault / result["saved"]
    assert note_path.exists()
    content = note_path.read_text()
    assert "zoom" in content
    assert "Key Outcomes" in content
    assert "Ashok to follow up" in content
