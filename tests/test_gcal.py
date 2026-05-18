"""Tests for Google Calendar integration (mocked API)."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch


def _mock_service(events):
    """Build a mock Google Calendar service that returns given events."""
    svc = MagicMock()
    svc.events().list().execute.return_value = {"items": events}
    return svc


def _make_event(summary: str, start_dt: str, end_dt: str) -> dict:
    return {
        "summary": summary,
        "start": {"dateTime": start_dt},
        "end": {"dateTime": end_dt},
        "htmlLink": "https://calendar.google.com/event/123",
    }


@patch("sophonic.tools.gcal._service")
def test_events_today_returns_events(mock_svc):
    from sophonic.tools.gcal import events_today

    mock_svc.return_value = _mock_service([
        _make_event("Standup", "2026-05-03T09:00:00Z", "2026-05-03T09:15:00Z"),
        _make_event("1-on-1", "2026-05-03T14:00:00Z", "2026-05-03T14:30:00Z"),
    ])

    result = events_today()
    assert len(result) == 2
    assert result[0]["title"] == "Standup"
    assert result[1]["title"] == "1-on-1"


@patch("sophonic.tools.gcal._service")
def test_events_today_empty(mock_svc):
    from sophonic.tools.gcal import events_today

    mock_svc.return_value = _mock_service([])
    result = events_today()
    assert result == []


@patch("sophonic.tools.gcal._service")
def test_events_range_passes_correct_dates(mock_svc):
    from sophonic.tools.gcal import events_range

    svc = _mock_service([])
    mock_svc.return_value = svc

    events_range(date(2026, 5, 1), date(2026, 5, 7))

    call_kwargs = svc.events().list.call_args.kwargs
    assert "2026-05-01" in call_kwargs["timeMin"]
    assert "2026-05-07" in call_kwargs["timeMax"]


@patch("sophonic.tools.gcal._service")
def test_events_include_location_and_description(mock_svc):
    from sophonic.tools.gcal import events_today

    event = _make_event("All Hands", "2026-05-03T10:00:00Z", "2026-05-03T11:00:00Z")
    event["location"] = "Room 101"
    event["description"] = "Monthly all-hands"
    mock_svc.return_value = _mock_service([event])

    result = events_today()
    assert result[0]["location"] == "Room 101"
    assert result[0]["description"] == "Monthly all-hands"
