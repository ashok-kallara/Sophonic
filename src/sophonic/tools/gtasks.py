"""Google Tasks integration — read-only.

Reads the user's open (incomplete) tasks across all task lists via the Google Tasks
API. Requires the `tasks.readonly` OAuth scope; if the signed-in token predates that
scope, the API returns 403 and this module surfaces a `needs_auth` hint telling the
user to add the scope and re-authenticate.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sophonic.google_auth import get_credentials

_SCOPE_FIX = (
    'sophonic config set google.scopes '
    '"https://www.googleapis.com/auth/calendar.readonly,'
    'https://www.googleapis.com/auth/gmail.readonly,'
    'https://www.googleapis.com/auth/tasks.readonly" '
    "&& sophonic auth google"
)


def _service():
    from googleapiclient.discovery import build
    return build("tasks", "v1", credentials=get_credentials())


def _parse_due(due: str | None) -> date | None:
    """Google Tasks `due` is RFC3339 (date-only, midnight UTC), e.g. 2026-08-04T00:00:00.000Z."""
    if not due:
        return None
    try:
        return date.fromisoformat(due[:10])
    except ValueError:
        return None


def list_open_tasks(max_lists: int = 20, max_tasks: int = 100) -> Any:
    """List open (incomplete) Google Tasks across all task lists.

    Returns a list of {id, title, notes, due, list, list_id}. On a missing-scope 403,
    returns a needs_auth dict with the fix command instead of raising.
    """
    try:
        svc = _service()
        lists = svc.tasklists().list(maxResults=max_lists).execute().get("items", [])
        out: list[dict[str, Any]] = []
        for tl in lists:
            resp = svc.tasks().list(
                tasklist=tl["id"],
                showCompleted=False,
                showHidden=False,
                maxResults=max_tasks,
            ).execute()
            for t in resp.get("items", []):
                title = (t.get("title") or "").strip()
                if not title:  # Google returns empty structural rows; skip them
                    continue
                out.append({
                    "id": t.get("id"),
                    "title": title,
                    "notes": t.get("notes", ""),
                    "due": _parse_due(t.get("due")),
                    "list": tl.get("title", ""),
                    "list_id": tl["id"],
                })
        return out
    except Exception as exc:  # noqa: BLE001 — normalize into a caller-friendly dict
        from googleapiclient.errors import HttpError

        if isinstance(exc, HttpError) and getattr(exc, "resp", None) and exc.resp.status == 403:
            return {
                "needs_auth": True,
                "detail": "Google Tasks needs the tasks.readonly scope, which your token lacks.",
                "run": _SCOPE_FIX,
            }
        return {"error": str(exc)}


TOOLS: dict[str, Any] = {
    "gtasks_list": list_open_tasks,
}
