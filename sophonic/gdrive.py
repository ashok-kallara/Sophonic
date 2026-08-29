"""Google Drive integration — comments and document/spreadsheet content (read-only).

Two independent read-only capabilities:

`list_mentioned_comments` — open comments where the caller is @mentioned or assigned.
Requires drive.readonly. Two-step: (1) drive.files.list — recent Docs/Sheets modified in
the last N days, or every Doc/Sheet the caller can see, paginated, when days=None (the
Drive API has no single call that searches comments across a whole Drive, so a full scan
means one comments.list call per file); (2) drive.comments.list — unresolved comments per
file, filtered for the caller's email in mentionedEmailAddresses or assigneeEmailAddress.
Note: adding a comment does not bump a file's modifiedTime (that field tracks content
edits only), so a day-bounded scan can miss a fresh mention on an old, otherwise-untouched
file — this is why callers may want the days=None full-scan escape hatch.

`search_content` — full-text search across Doc/Sheet content. Drive's `fullText contains`
query is a single indexed search covering everything the caller can see, so unlike
comments there's no recency tiering needed. Requires drive.readonly (Docs, via Drive's
own export) and spreadsheets.readonly (Sheets, via the Sheets API, read across every tab —
Drive's own export for spreadsheets only returns the first tab).
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
    'https://www.googleapis.com/auth/drive.readonly,'
    'https://www.googleapis.com/auth/spreadsheets.readonly" '
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


def _sheets_service():
    from googleapiclient.discovery import build
    return build("sheets", "v4", credentials=get_credentials())


def _user_email(svc: Any) -> str:
    about = svc.about().get(fields="user(emailAddress)").execute()
    return about["user"]["emailAddress"]


def _doc_text(svc: Any, file_id: str) -> str:
    """Export a Google Doc's full body as plain text (drive.readonly is enough)."""
    data = svc.files().export(fileId=file_id, mimeType="text/plain").execute()
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)


def _sheet_text(sheets_svc: Any, file_id: str) -> str:
    """Every tab's cell values as text — not just the first tab (needs spreadsheets.readonly).

    Drive's own files.export for spreadsheets only returns the first sheet as CSV; the
    Sheets API is the only way to read every tab.
    """
    meta = sheets_svc.spreadsheets().get(
        spreadsheetId=file_id, fields="sheets.properties.title"
    ).execute()
    lines: list[str] = []
    for sheet in meta.get("sheets", []):
        title = sheet["properties"]["title"]
        resp = sheets_svc.spreadsheets().values().get(
            spreadsheetId=file_id, range=title
        ).execute()
        for row in resp.get("values", []):
            line = "\t".join(str(cell) for cell in row).strip()
            if line:
                lines.append(line)
    return "\n".join(lines)


def _excerpt(text: str, query: str, context_chars: int) -> str:
    """A window of text around the first match of `query`, or a leading preview if none.

    Drive's fullText search is a tokenized/fuzzy match, not a literal substring search,
    so the exact query string doesn't always reappear verbatim in the exported text —
    fall back to a preview rather than returning nothing.
    """
    idx = text.lower().find(query.lower())
    if idx == -1:
        preview = text[: context_chars * 2].strip()
        return preview + ("…" if len(text) > context_chars * 2 else "")
    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(query) + context_chars)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


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


def _fetch_error(exc: Exception) -> dict[str, Any]:
    """Normalize an exception from a single file's content fetch into a result dict.

    Distinguishes "the Sheets/Drive API isn't enabled for this project" from "the token
    lacks a scope" the same way the top-level handlers do, but scoped to one file so a
    partial failure (e.g. Sheets not consented yet) doesn't have to take down every
    already-fetched Doc result alongside it.
    """
    from googleapiclient.errors import HttpError

    if isinstance(exc, HttpError) and getattr(exc, "resp", None) and exc.resp.status == 403:
        raw = (exc.content or b"").decode("utf-8", "replace")
        if any(k in raw for k in ("SERVICE_DISABLED", "accessNotConfigured", "has not been used")):
            service = "Sheets" if "sheets.googleapis.com" in raw else "Drive"
            url = "sheets" if service == "Sheets" else "drive"
            return {
                "error": (
                    f"The Google {service} API is not enabled for your OAuth project. Enable it "
                    f"at https://console.cloud.google.com/apis/library/{url}.googleapis.com and "
                    "retry (allow a minute to propagate)."
                ),
            }
        return {
            "needs_auth": True,
            "detail": (
                "Reading this file needs the drive.readonly and spreadsheets.readonly scopes, "
                "which your token lacks."
            ),
            "run": _SCOPE_FIX,
        }
    return {"error": str(exc)}


def search_content(query: str, max_files: int = 20, context_chars: int = 200) -> Any:
    """Full-text search Doc/Sheet content and return an excerpt per match.

    Uses Drive's `fullText contains` search, which is a single indexed query across
    every Doc/Sheet the caller can see — unlike list_mentioned_comments, there's no
    recent-vs-full-scan tiering to do here; it's already whole-Drive by default. Docs
    are read via Drive's own export (drive.readonly is enough); Sheets are read via the
    Sheets API across every tab, not just the first one Drive's export would give you —
    this needs the spreadsheets.readonly scope.

    Returns a list of {file_id, file_name, file_type, file_link, excerpt}, most recently
    modified first. A file whose content couldn't be fetched (e.g. Sheets not yet
    consented) gets `excerpt: None` plus `needs_auth`/`error` on that entry instead of
    failing the whole search — a common transitional state when only one of the two
    scopes has been granted so far. If the initial search itself fails (e.g. drive.readonly
    missing), the whole call returns a top-level needs_auth/error dict instead of a list.
    """
    try:
        svc = _service()
        escaped = query.replace("\\", "\\\\").replace("'", "\\'")
        mime_filter = f"(mimeType='{_MIME_DOCUMENT}' or mimeType='{_MIME_SPREADSHEET}')"
        q = f"{mime_filter} and trashed=false and fullText contains '{escaped}'"

        files_resp = svc.files().list(
            q=q,
            fields=_FILE_FIELDS,
            orderBy="modifiedTime desc",
            pageSize=max_files,
        ).execute()
    except Exception as exc:  # noqa: BLE001 — normalize into a caller-friendly dict
        return _fetch_error(exc)

    sheets_svc = None
    out: list[dict[str, Any]] = []
    for f in files_resp.get("files", []):
        file_id = f["id"]
        is_doc = f["mimeType"] == _MIME_DOCUMENT
        file_type = "document" if is_doc else "spreadsheet"
        entry: dict[str, Any] = {
            "file_id": file_id,
            "file_name": f.get("name", ""),
            "file_type": file_type,
            "file_link": f.get("webViewLink", ""),
        }
        try:
            if is_doc:
                text = _doc_text(svc, file_id)
            else:
                if sheets_svc is None:
                    sheets_svc = _sheets_service()
                text = _sheet_text(sheets_svc, file_id)
            entry["excerpt"] = _excerpt(text, query, context_chars)
        except Exception as exc:  # noqa: BLE001 — degrade this entry, keep the rest
            entry["excerpt"] = None
            entry.update(_fetch_error(exc))
        out.append(entry)

    return out
