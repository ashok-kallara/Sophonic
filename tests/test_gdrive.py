"""Tests for the Google Drive comments integration (filtering, scope-error handling)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class _FakeDriveApi:
    """Minimal stand-in for the googleapiclient Drive v3 service.

    `files` may be a flat list (returned in one page) or a list of pages (each a list
    of file dicts) to exercise pagination; `file_list_calls` records every
    `files().list()` kwargs call so tests can assert on the query/pageSize/pageToken
    actually sent.
    """

    def __init__(
        self,
        user_email: str,
        files: list,
        comments_by_file: dict,
        doc_text_by_file: dict | None = None,
    ):
        self._user_email = user_email
        self._pages = files if files and isinstance(files[0], list) else [files]
        self._comments_by_file = comments_by_file
        self._doc_text_by_file = doc_text_by_file or {}
        self.file_list_calls: list[dict] = []
        self.comments_list_calls: list[dict] = []
        self.export_calls: list[dict] = []

    def about(self):
        api = MagicMock()
        api.get.return_value.execute.return_value = {"user": {"emailAddress": self._user_email}}
        return api

    def files(self):
        outer = self

        class _Files:
            def list(self, **kwargs):
                outer.file_list_calls.append(kwargs)
                page_index = len(outer.file_list_calls) - 1
                m = MagicMock()
                page = outer._pages[page_index] if page_index < len(outer._pages) else []
                resp = {"files": page}
                if page_index + 1 < len(outer._pages):
                    resp["nextPageToken"] = f"page-{page_index + 1}"
                m.execute.return_value = resp
                return m

            def export(self, fileId, mimeType):
                outer.export_calls.append({"fileId": fileId, "mimeType": mimeType})
                m = MagicMock()
                m.execute.return_value = outer._doc_text_by_file.get(fileId, "").encode("utf-8")
                return m

        return _Files()

    def comments(self):
        outer = self

        class _Comments:
            def list(self, fileId, **kwargs):
                outer.comments_list_calls.append({"fileId": fileId, **kwargs})
                m = MagicMock()
                m.execute.return_value = {"comments": outer._comments_by_file.get(fileId, [])}
                return m

        return _Comments()


class _FakeSheetsApi:
    """Minimal stand-in for the googleapiclient Sheets v4 service.

    `tabs_by_file` maps file_id -> {tab_title: [[row values], ...]}, so a test can give
    a spreadsheet more than one tab and assert every tab got read. `raise_on_get` lets a
    test simulate the Sheets API being unavailable (e.g. not yet consented/enabled).
    """

    def __init__(self, tabs_by_file: dict, raise_on_get: Exception | None = None):
        self._tabs_by_file = tabs_by_file
        self._raise_on_get = raise_on_get
        self.values_get_calls: list[dict] = []

    def spreadsheets(self):
        outer = self

        class _Values:
            def get(self, spreadsheetId, range):
                outer.values_get_calls.append({"spreadsheetId": spreadsheetId, "range": range})
                m = MagicMock()
                rows = outer._tabs_by_file.get(spreadsheetId, {}).get(range, [])
                m.execute.return_value = {"values": rows}
                return m

        class _Spreadsheets:
            def get(self, spreadsheetId, fields):
                if outer._raise_on_get:
                    raise outer._raise_on_get
                m = MagicMock()
                titles = list(outer._tabs_by_file.get(spreadsheetId, {}).keys())
                m.execute.return_value = {
                    "sheets": [{"properties": {"title": t}} for t in titles]
                }
                return m

            def values(self):
                return _Values()

        return _Spreadsheets()


_ME = "me@example.com"
_OTHER = "other@example.com"

_FAKE_DOC = {
    "id": "doc1",
    "name": "Q3 Budget",
    "mimeType": "application/vnd.google-apps.document",
    "webViewLink": "https://docs.google.com/document/d/doc1/edit",
}
_FAKE_SHEET = {
    "id": "sheet1",
    "name": "Data Model",
    "mimeType": "application/vnd.google-apps.spreadsheet",
    "webViewLink": "https://docs.google.com/spreadsheets/d/sheet1/edit",
}


def _make_comment(
    cid: str,
    content: str,
    mentions: list[str] | None = None,
    assignee: str | None = None,
    resolved: bool = False,
    replies: int = 0,
) -> dict:
    return {
        "id": cid,
        "author": {"displayName": "Alice", "emailAddress": _OTHER, "me": False},
        "content": content,
        "resolved": resolved,
        "mentionedEmailAddresses": mentions or [],
        "assigneeEmailAddress": assignee,
        "createdTime": "2026-08-01T10:00:00.000Z",
        "modifiedTime": "2026-08-01T10:00:00.000Z",
        "replies": [{"id": f"r{i}"} for i in range(replies)],
    }


def test_mentioned_comment_is_returned(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(
        user_email=_ME,
        files=[_FAKE_DOC],
        comments_by_file={
            "doc1": [_make_comment("c1", "Please review @me", mentions=[_ME])],
        },
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    result = gdrive.list_mentioned_comments()
    assert len(result) == 1
    c = result[0]
    assert c["file_name"] == "Q3 Budget"
    assert c["file_type"] == "document"
    assert c["file_link"] == "https://docs.google.com/document/d/doc1/edit"
    assert c["comment_id"] == "c1"
    assert c["content"] == "Please review @me"
    assert c["is_assigned"] is False
    assert _ME in c["mentions"]


def test_assigned_comment_is_returned(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(
        user_email=_ME,
        files=[_FAKE_SHEET],
        comments_by_file={
            "sheet1": [_make_comment("c2", "Fix this cell", assignee=_ME)],
        },
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    result = gdrive.list_mentioned_comments()
    assert len(result) == 1
    assert result[0]["is_assigned"] is True
    assert result[0]["file_type"] == "spreadsheet"


def test_resolved_comment_is_skipped(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(
        user_email=_ME,
        files=[_FAKE_DOC],
        comments_by_file={
            "doc1": [_make_comment("c3", "Already done", mentions=[_ME], resolved=True)],
        },
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    assert gdrive.list_mentioned_comments() == []


def test_comment_not_mentioning_me_is_skipped(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(
        user_email=_ME,
        files=[_FAKE_DOC],
        comments_by_file={
            "doc1": [_make_comment("c4", "Hey @other", mentions=[_OTHER])],
        },
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    assert gdrive.list_mentioned_comments() == []


def test_reply_count_is_captured(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(
        user_email=_ME,
        files=[_FAKE_DOC],
        comments_by_file={
            "doc1": [_make_comment("c5", "LGTM?", mentions=[_ME], replies=3)],
        },
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    result = gdrive.list_mentioned_comments()
    assert result[0]["reply_count"] == 3


def test_default_days_filters_query_and_comments_by_time(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(user_email=_ME, files=[_FAKE_DOC], comments_by_file={})
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    gdrive.list_mentioned_comments(days=30)

    assert "modifiedTime >" in fake.file_list_calls[0]["q"]
    assert "startModifiedTime" in fake.comments_list_calls[0]


def test_days_none_is_a_full_scan_with_no_time_filter(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(user_email=_ME, files=[_FAKE_DOC], comments_by_file={})
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    gdrive.list_mentioned_comments(days=None, max_files=50)

    assert "modifiedTime >" not in fake.file_list_calls[0]["q"]
    assert "startModifiedTime" not in fake.comments_list_calls[0]


def test_full_scan_paginates_across_multiple_pages(monkeypatch):
    from sophonic import gdrive

    doc_a = {**_FAKE_DOC, "id": "docA"}
    doc_b = {**_FAKE_DOC, "id": "docB"}
    doc_c = {**_FAKE_DOC, "id": "docC"}
    fake = _FakeDriveApi(
        user_email=_ME,
        files=[[doc_a, doc_b], [doc_c]],  # two pages
        comments_by_file={
            "docA": [_make_comment("c1", "hi @me", mentions=[_ME])],
            "docC": [_make_comment("c2", "hi @me too", mentions=[_ME])],
        },
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    result = gdrive.list_mentioned_comments(days=None, max_files=10)

    assert len(fake.file_list_calls) == 2  # followed nextPageToken once
    assert {c["comment_id"] for c in result} == {"c1", "c2"}


def test_max_files_caps_total_across_pages(monkeypatch):
    from sophonic import gdrive

    docs = [{**_FAKE_DOC, "id": f"doc{i}"} for i in range(5)]
    fake = _FakeDriveApi(
        user_email=_ME,
        files=[docs[:3], docs[3:]],  # two pages, 3 + 2 files
        comments_by_file={},
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    gdrive.list_mentioned_comments(days=None, max_files=3)

    # only the first page was needed to satisfy max_files=3
    assert len(fake.file_list_calls) == 1
    assert len(fake.comments_list_calls) == 3


def test_search_content_builds_fulltext_query_and_returns_excerpt(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(
        user_email=_ME,
        files=[_FAKE_DOC],
        comments_by_file={},
        doc_text_by_file={"doc1": "Intro. " + ("padding " * 50) + "the Q3 budget is tight this year." + (" more" * 50)},
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    result = gdrive.search_content("Q3 budget", max_files=10, context_chars=20)

    assert "fullText contains 'Q3 budget'" in fake.file_list_calls[0]["q"]
    assert fake.export_calls == [{"fileId": "doc1", "mimeType": "text/plain"}]
    assert len(result) == 1
    assert result[0]["file_type"] == "document"
    assert result[0]["file_name"] == "Q3 Budget"
    assert "Q3 budget is tight" in result[0]["excerpt"]
    assert result[0]["excerpt"].startswith("…")  # truncated before the match


def test_search_content_escapes_single_quotes_in_query(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(user_email=_ME, files=[_FAKE_DOC], comments_by_file={}, doc_text_by_file={"doc1": "x"})
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    gdrive.search_content("bob's plan")

    assert "bob\\'s plan" in fake.file_list_calls[0]["q"]


def test_search_content_falls_back_to_preview_when_no_literal_match(monkeypatch):
    from sophonic import gdrive

    fake = _FakeDriveApi(
        user_email=_ME,
        files=[_FAKE_DOC],
        comments_by_file={},
        doc_text_by_file={"doc1": "Some unrelated-looking text that Drive's fuzzy match found relevant."},
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake)

    result = gdrive.search_content("totally different phrase", context_chars=10)

    assert result[0]["excerpt"].startswith("Some unrelated")


def test_search_content_reads_every_sheet_tab_not_just_the_first(monkeypatch):
    from sophonic import gdrive

    fake_drive = _FakeDriveApi(user_email=_ME, files=[_FAKE_SHEET], comments_by_file={})
    fake_sheets = _FakeSheetsApi(
        tabs_by_file={
            "sheet1": {
                "Sheet1": [["header"], ["irrelevant row"]],
                "Q3 Tab": [["budget"], ["the target number is 42000"]],
            }
        }
    )
    monkeypatch.setattr(gdrive, "_service", lambda: fake_drive)
    monkeypatch.setattr(gdrive, "_sheets_service", lambda: fake_sheets)

    result = gdrive.search_content("42000", context_chars=20)

    tabs_read = {c["range"] for c in fake_sheets.values_get_calls}
    assert tabs_read == {"Sheet1", "Q3 Tab"}  # not just the first tab
    assert result[0]["file_type"] == "spreadsheet"
    assert "42000" in result[0]["excerpt"]


def test_search_content_partial_failure_keeps_successful_entries(monkeypatch):
    """A common transitional state: drive.readonly granted, spreadsheets.readonly not
    yet consented. The Doc match must still come back with its excerpt; only the Sheet
    entry should degrade — the whole call must not fail just because one file did."""
    from sophonic import gdrive
    from googleapiclient.errors import HttpError

    doc = {**_FAKE_DOC, "id": "doc1"}
    sheet = {**_FAKE_SHEET, "id": "sheet1"}
    fake_drive = _FakeDriveApi(
        user_email=_ME,
        files=[doc, sheet],
        comments_by_file={},
        doc_text_by_file={"doc1": "the Q3 budget details are here"},
    )
    resp = MagicMock()
    resp.status = 403
    sheets_error = HttpError(
        resp=resp,
        content=b'{"error":{"status":"PERMISSION_DENIED","message":"Google Sheets API has not been used in project 123. SERVICE_DISABLED"}}',
    )
    fake_sheets = _FakeSheetsApi(tabs_by_file={}, raise_on_get=sheets_error)
    monkeypatch.setattr(gdrive, "_service", lambda: fake_drive)
    monkeypatch.setattr(gdrive, "_sheets_service", lambda: fake_sheets)

    result = gdrive.search_content("Q3 budget")

    assert len(result) == 2
    doc_entry = next(r for r in result if r["file_type"] == "document")
    sheet_entry = next(r for r in result if r["file_type"] == "spreadsheet")
    assert "Q3 budget" in doc_entry["excerpt"]
    assert "error" not in doc_entry
    assert sheet_entry["excerpt"] is None
    assert "not enabled" in sheet_entry["error"]


def test_search_content_scope_error_returns_needs_auth(monkeypatch):
    from sophonic import gdrive
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = 403

    def boom():
        raise HttpError(resp=resp, content=b"insufficient scope for spreadsheets")

    monkeypatch.setattr(gdrive, "_service", boom)
    result = gdrive.search_content("anything")
    assert result["needs_auth"] is True
    assert "spreadsheets.readonly" in result["detail"]
    assert "spreadsheets.readonly" in result["run"]


def test_scope_error_returns_needs_auth(monkeypatch):
    from sophonic import gdrive
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = 403

    def boom():
        raise HttpError(resp=resp, content=b"insufficient scope for drive")

    monkeypatch.setattr(gdrive, "_service", boom)
    result = gdrive.list_mentioned_comments()
    assert result["needs_auth"] is True
    assert "drive.readonly" in result["detail"]
    assert "drive.readonly" in result["run"]


def test_api_disabled_returns_enable_hint(monkeypatch):
    from sophonic import gdrive
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = 403

    def boom():
        raise HttpError(
            resp=resp,
            content=b'{"error":{"status":"PERMISSION_DENIED","message":"Google Drive API has not been used in project 123. SERVICE_DISABLED"}}',
        )

    monkeypatch.setattr(gdrive, "_service", boom)
    result = gdrive.list_mentioned_comments()
    assert "needs_auth" not in result
    assert "not enabled" in result["error"]
    assert "console.cloud.google.com" in result["error"]
