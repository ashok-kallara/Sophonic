"""Google Calendar integration."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from akashic.google_auth import get_credentials


def _service():
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=get_credentials())


def events_today() -> list[dict[str, Any]]:
    """Return today's calendar events."""
    today = date.today()
    return events_range(today, today)


def events_range(start: date, end: date) -> list[dict[str, Any]]:
    """Return calendar events between start and end (inclusive)."""
    svc = _service()
    time_min = datetime(start.year, start.month, start.day, tzinfo=timezone.utc).isoformat()
    time_max = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()
    result = svc.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=50,
    ).execute()
    items = result.get("items", [])
    return [
        {
            "title": e.get("summary", "(No title)"),
            "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
            "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
            "location": e.get("location"),
            "description": e.get("description"),
            "link": e.get("htmlLink"),
        }
        for e in items
    ]


TOOLS: dict[str, Any] = {
    "gcal_events_today": events_today,
    "gcal_events_range": events_range,
}
