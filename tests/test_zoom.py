"""Tests for the Zoom AI-notes tools (cookie parsing, title split, save)."""

from unittest.mock import patch

from freezegun import freeze_time


def test_parse_cookies_to_playwright_dicts():
    from sophonic.tools.zoom import _parse_cookies

    cookies = _parse_cookies("_zm_ssid=abc; zm_aid=def ; empty")
    names = {c["name"]: c["value"] for c in cookies}
    assert names == {"_zm_ssid": "abc", "zm_aid": "def"}
    assert all(c["domain"] == ".zoom.us" and c["path"] == "/" and c["secure"] for c in cookies)


def test_parse_cookies_strips_leading_cookie_header_label():
    from sophonic.tools.zoom import _parse_cookies

    # Pasting the whole request-header line, label included, must still parse cleanly.
    cookies = _parse_cookies("Cookie: _zm_ssid=abc; zm_aid=def")
    names = {c["name"]: c["value"] for c in cookies}
    assert names == {"_zm_ssid": "abc", "zm_aid": "def"}
    assert all(not c["name"].lower().startswith("cookie") for c in cookies)


def test_split_title_extracts_meeting_and_date():
    from sophonic.tools.zoom import _split_title

    meeting, iso = _split_title("Data Leads Weekly 2026-07-31 13:33(GMT-4:00)")
    assert meeting == "Data Leads Weekly"
    assert iso == "2026-07-31"

    meeting, iso = _split_title("Untitled note")
    assert meeting == "Untitled note"
    assert iso is None


class _Resp:
    def __init__(self, status, location=""):
        self.status_code = status
        self.headers = {"location": location} if location else {}
        self.is_redirect = 300 <= status < 400 and bool(location)


def test_check_auth_valid_when_200(monkeypatch):
    from sophonic.tools import zoom

    monkeypatch.setenv("ZOOM_COOKIES", "_zm=abc")
    monkeypatch.setattr(zoom.httpx, "get", lambda *a, **k: _Resp(200))
    result = zoom.check_auth()
    assert result["ok"] is True


def test_check_auth_expired_on_signin_redirect(monkeypatch):
    from sophonic.tools import zoom

    monkeypatch.setenv("ZOOM_COOKIES", "_zm=abc")
    monkeypatch.setattr(zoom.httpx, "get", lambda *a, **k: _Resp(302, "https://zoom.us/signin"))
    result = zoom.check_auth()
    assert result["ok"] is False
    assert "expired" in result["detail"]


def test_check_auth_missing_cookies(monkeypatch):
    from sophonic.tools import zoom

    monkeypatch.delenv("ZOOM_COOKIES", raising=False)
    result = zoom.check_auth()
    assert result["ok"] is False
    assert "not set" in result["detail"]


def test_check_auth_handles_request_error(monkeypatch):
    from sophonic.tools import zoom

    monkeypatch.setenv("ZOOM_COOKIES", "_zm=abc")

    def boom(*a, **k):
        raise zoom.httpx.HTTPError("network down")

    monkeypatch.setattr(zoom.httpx, "get", boom)
    result = zoom.check_auth()
    assert result["ok"] is False
    assert "failed" in result["detail"]


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


def test_extract_action_items_from_note_text():
    from sophonic.tools.zoom import _extract_action_items

    text = (
        "Quick recap\n"
        "The team discussed the roadmap.\n"
        "\n"
        "Action Items\n"
        "- Ashok to send the design doc\n"
        "- Priya to schedule the follow-up\n"
        "\n"
        "Details\n"
        "Lots of prose here that is not a task.\n"
    )
    assert _extract_action_items(text) == [
        "Ashok to send the design doc",
        "Priya to schedule the follow-up",
    ]


def test_extract_action_items_spans_adjacent_headings():
    from sophonic.tools.zoom import _extract_action_items

    text = "Action Items\n- Do A\nNext Steps\n1. Do B\nSummary\nnot a task"
    assert _extract_action_items(text) == ["Do A", "Do B"]


def test_extract_action_items_drops_narrative_prose():
    from sophonic.tools.zoom import _extract_action_items

    # Only bulleted/numbered entries under the heading become tasks; prose is dropped.
    text = (
        "Action Items\n"
        "The team agreed to move forward with the plan.\n"   # prose, not a task
        "- Ship the doc\n"
        "Owner will coordinate offline.\n"                    # prose, not a task
        "- Book the room\n"
    )
    assert _extract_action_items(text) == ["Ship the doc", "Book the room"]


def test_action_items_needs_cookies(monkeypatch):
    from sophonic.tools import zoom

    monkeypatch.delenv("ZOOM_COOKIES", raising=False)
    result = zoom.action_items()
    assert result["needs_auth"] is True


@freeze_time("2026-08-03")
def test_action_items_defaults_to_today(use_fixture_vault, monkeypatch):
    from sophonic.tools import zoom
    from sophonic.tools.obsidian import get_daily_note

    monkeypatch.setenv("ZOOM_COOKIES", "_zm=abc")
    monkeypatch.setattr(zoom, "notes", lambda limit=50: [
        {"id": "A", "meeting": "Standup", "date": "2026-08-03", "link": "https://docs.zoom.us/doc/A"},
        {"id": "B", "meeting": "Old Sync", "date": "2026-07-01"},
    ])
    monkeypatch.setattr(zoom, "note", lambda doc_id: {"id": doc_id, "text": f"Action Items\n- Do the thing for {doc_id}"})

    result = zoom.action_items()
    assert result["range"] == {"start": "2026-08-03", "end": "2026-08-03"}
    assert result["meetings_scanned"] == 1  # only today's meeting is in range
    assert result["count"] == 1
    content = get_daily_note()
    # Grouped under a dedicated section with a linked meeting subheading.
    assert "## Meeting Action Items" in content
    assert "### [Standup — 2026-08-03](https://docs.zoom.us/doc/A)" in content
    assert "- [ ] Do the thing for A #zoom" in content
    assert "Do the thing for B" not in content


@freeze_time("2026-08-03")
def test_action_items_heading_falls_back_to_plain_text(use_fixture_vault, monkeypatch):
    from sophonic.tools import zoom
    from sophonic.tools.obsidian import get_daily_note

    monkeypatch.setenv("ZOOM_COOKIES", "_zm=abc")
    monkeypatch.setattr(zoom, "notes", lambda limit=50: [{"id": "A", "meeting": "Standup", "date": "2026-08-03"}])
    monkeypatch.setattr(zoom, "note", lambda doc_id: {"id": doc_id, "text": "Action Items\n- Do the thing"})

    zoom.action_items()
    content = get_daily_note()
    assert "### Standup — 2026-08-03" in content        # plain heading, no link
    assert "- [ ] Do the thing #zoom" in content


@freeze_time("2026-08-03")
def test_action_items_last_3_days(use_fixture_vault, monkeypatch):
    from sophonic.tools import zoom

    monkeypatch.setenv("ZOOM_COOKIES", "_zm=abc")
    monkeypatch.setattr(zoom, "notes", lambda limit=50: [
        {"id": "A", "meeting": "M1", "date": "2026-08-03"},
        {"id": "B", "meeting": "M2", "date": "2026-08-01"},
        {"id": "C", "meeting": "M3", "date": "2026-07-20"},
    ])
    monkeypatch.setattr(zoom, "note", lambda doc_id: {"id": doc_id, "text": f"Action Items\n- Task {doc_id}"})

    result = zoom.action_items(days=3)
    assert result["range"] == {"start": "2026-08-01", "end": "2026-08-03"}
    assert result["meetings_scanned"] == 2  # A and B, not C
    assert len(result["groups"]) == 2       # one group per in-range meeting


@freeze_time("2026-08-03")
def test_action_items_dry_run_and_dedupe(use_fixture_vault, monkeypatch):
    from sophonic.tools import zoom
    from sophonic.tools.obsidian import get_daily_note

    monkeypatch.setenv("ZOOM_COOKIES", "_zm=abc")
    monkeypatch.setattr(zoom, "notes", lambda limit=50: [{"id": "A", "meeting": "M", "date": "2026-08-03"}])
    monkeypatch.setattr(zoom, "note", lambda doc_id: {"id": doc_id, "text": "Action Items\n- Repeat task"})

    dry = zoom.action_items(dry_run=True)
    assert dry["dry_run"] is True and dry["count"] == 1
    assert "Repeat task" not in get_daily_note()  # dry run wrote nothing

    zoom.action_items()                      # writes once
    again = zoom.action_items()              # deduped on re-run
    assert again["count"] == 0
    assert get_daily_note().count("Repeat task") == 1


@freeze_time("2026-08-03")
def test_action_items_owner_filter(use_fixture_vault, monkeypatch):
    from sophonic.tools import zoom

    monkeypatch.setenv("ZOOM_COOKIES", "_zm=abc")
    monkeypatch.setattr(zoom, "notes", lambda limit=50: [{"id": "A", "meeting": "M", "date": "2026-08-03"}])
    monkeypatch.setattr(zoom, "note", lambda doc_id: {
        "id": doc_id, "text": "Action Items\n- Ashok to review PR\n- Priya to book room",
    })

    result = zoom.action_items(owner="ashok")
    assert result["count"] == 1
    assert result["groups"][0]["items"] == ["Ashok to review PR"]


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
