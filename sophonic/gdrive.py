"""Google Drive integration — open comments mentioning the authenticated user (read-only).

Requires the drive.readonly OAuth scope. Two-step approach:
  1. drive.files.list — recent Docs and Sheets modified in the last N days (or every
     Doc/Sheet the caller can see, paginated, when days=None — the Drive API has no
     single call that searches comments across a whole Drive, so a full scan means one
     comments.list call per file).
  2. drive.comments.list — unresolved comments per file.
Filter in-step-2 for comments where the user's email is in mentionedEmailAddresses
or equals assigneeEmailAddress.

Note: adding a comment does not bump a file's modifiedTime (that field tracks content
edits only), so a day-bounded scan can miss a fresh mention on an old, otherwise-untouched
file — this is why callers may want the days=None full-scan escape hatch.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sophonic.google_auth import get_credentials

_SCOPE_FIX = (
    'uv run python scripts/config.py set google.scopes '
    '"https://www.googleapis.com/auth/calendar.readonly,'
    'https://www.googleapis.com/auth/gmail.readonly,'
    'https://www.googleapis.com/auth/tasks.readonly,'
    'https://www.googleapis.com/auth/drive.readonly" '
    "&& uv run python scripts/auth.py google"
)

_MIME_DOCUMENT = "application/vnd.google-apps.document"
_MIME_SPREADSHEET = "application/vnd.google-apps.spreadsheet"

_FILE_FIELDS = "files(id,name,mimeType,webViewLink)"
_COMMENT_FIELDS = (
    "comments("
    "id,author(displayName,emailAddress,me),content,resolved,"
    "mentionedEmailAddresses,assigneeEmailAddress,"
    "createdTime,modifiedTime,replies(id)"
    ")"
)


def _service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=get_credentials())


def _user_email(svc: Any) -> str:
    about = svc.about().get(fields="user(emailAddress)").execute()
    return about["user"]["emailAddress"]


def list_mentioned_comments(days: int | None = 30, max_files: int = 50) -> Any:
    """Return open (unresolved) comments in Docs/Sheets where the user is @mentioned or assigned.

    `days=None` drops the modifiedTime filter entirely and paginates through every
    Doc/Sheet the caller can see (up to `max_files`) — a full-Drive scan, for use when a
    day-bounded pass finds nothing. Otherwise behaves as before: the `max_files` most
    recently modified matching files, and comments modified within `days`.

    Returns a list of {file_id, file_name, file_type, file_link, comment_id, author,
    author_email, content, created, modified, is_assigned, mentions, reply_count}.
    On a missing-scope 403, returns a needs_auth dict instead of raising.
    """
    try:
        svc = _service()
        me = _user_email(svc)

        cutoff = None
        if days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        mime_filter = f"(mimeType='{_MIME_DOCUMENT}' or mimeType='{_MIME_SPREADSHEET}')"
        q = f"{mime_filter} and trashed=false"
        if cutoff:
            q += f" and modifiedTime > '{cutoff}'"

        files: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(files) < max_files:
            resp = svc.files().list(
                q=q,
                fields=f"nextPageToken,{_FILE_FIELDS}",
                orderBy="modifiedTime desc",
                pageSize=min(1000, max_files - len(files)),
                pageToken=page_token,
            ).execute()
            files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        files = files[:max_files]

        out: list[dict[str, Any]] = []
        for f in files:
            file_id = f["id"]
            file_type = "document" if f["mimeType"] == _MIME_DOCUMENT else "spreadsheet"

            comments_kwargs: dict[str, Any] = {
                "fileId": file_id,
                "includeDeleted": False,
                "fields": _COMMENT_FIELDS,
                "pageSize": 100,
            }
            if cutoff:
                comments_kwargs["startModifiedTime"] = cutoff
            comments_resp = svc.comments().list(**comments_kwargs).execute()

            for c in comments_resp.get("comments", []):
                if c.get("resolved"):
                    continue
                mentions: list[str] = c.get("mentionedEmailAddresses") or []
                assignee: str | None = c.get("assigneeEmailAddress")
                is_mentioned = me in mentions
                is_assigned = assignee == me
                if not (is_mentioned or is_assigned):
                    continue
                author = c.get("author") or {}
                out.append({
                    "file_id": file_id,
                    "file_name": f.get("name", ""),
                    "file_type": file_type,
                    "file_link": f.get("webViewLink", ""),
                    "comment_id": c.get("id"),
                    "author": author.get("displayName", ""),
                    "author_email": author.get("emailAddress", ""),
                    "content": c.get("content", ""),
                    "created": c.get("createdTime"),
                    "modified": c.get("modifiedTime"),
                    "is_assigned": is_assigned,
                    "mentions": mentions,
                    "reply_count": len(c.get("replies") or []),
                })

        return out

    except Exception as exc:  # noqa: BLE001 — normalize into a caller-friendly dict
        from googleapiclient.errors import HttpError

        if isinstance(exc, HttpError) and getattr(exc, "resp", None) and exc.resp.status == 403:
            raw = (exc.content or b"").decode("utf-8", "replace")
            if any(k in raw for k in ("SERVICE_DISABLED", "accessNotConfigured", "has not been used")):
                return {
                    "error": (
                        "Google Drive API is not enabled for your OAuth project. Enable it at "
                        "https://console.cloud.google.com/apis/library/drive.googleapis.com "
                        "and retry (allow a minute to propagate)."
                    ),
                }
            return {
                "needs_auth": True,
                "detail": "Google Drive needs the drive.readonly scope, which your token lacks.",
                "run": _SCOPE_FIX,
            }
        return {"error": str(exc)}
