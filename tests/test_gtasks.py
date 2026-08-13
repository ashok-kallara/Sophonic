"""Tests for the Google Tasks tool (parsing, filtering, scope-error handling)."""

from datetime import date
from unittest.mock import MagicMock

import pytest


class _FakeTasksApi:
    """Minimal stand-in for the googleapiclient Tasks service."""

    def __init__(self, lists, tasks_by_list):
        self._lists = lists
        self._tasks_by_list = tasks_by_list

    def tasklists(self):
        api = MagicMock()
        api.list.return_value.execute.return_value = {"items": self._lists}
        return api

    def tasks(self):
        outer = self

        class _Tasks:
            def list(self, tasklist, **kwargs):
                ex = MagicMock()
                ex.execute.return_value = {"items": outer._tasks_by_list.get(tasklist, [])}
                return ex

        return _Tasks()


def test_list_open_tasks_parses_and_maps(monkeypatch):
    from sophonic import gtasks

    fake = _FakeTasksApi(
        lists=[{"id": "L1", "title": "Work"}, {"id": "L2", "title": "Home"}],
        tasks_by_list={
            "L1": [
                {"id": "t1", "title": "Ship it", "due": "2026-08-05T00:00:00.000Z", "notes": "n"},
                {"id": "blank", "title": "  "},  # structural empty row — skipped
            ],
            "L2": [{"id": "t2", "title": "Buy milk"}],
        },
    )
    monkeypatch.setattr(gtasks, "_service", lambda: fake)

    result = gtasks.list_open_tasks()
    assert [t["title"] for t in result] == ["Ship it", "Buy milk"]
    ship = result[0]
    assert ship["due"] == date(2026, 8, 5)
    assert ship["list"] == "Work"
    assert result[1]["due"] is None


def test_list_open_tasks_scope_error_returns_needs_auth(monkeypatch):
    from sophonic import gtasks
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = 403

    def boom():
        raise HttpError(resp=resp, content=b"insufficient scope")

    monkeypatch.setattr(gtasks, "_service", boom)
    result = gtasks.list_open_tasks()
    assert result["needs_auth"] is True
    assert "tasks.readonly" in result["run"]


def test_list_open_tasks_api_disabled_returns_enable_hint(monkeypatch):
    from sophonic import gtasks
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = 403

    def boom():
        raise HttpError(resp=resp, content=b'{"error":{"status":"PERMISSION_DENIED","message":"Google Tasks API has not been used in project 123 before or it is disabled. SERVICE_DISABLED"}}')

    monkeypatch.setattr(gtasks, "_service", boom)
    result = gtasks.list_open_tasks()
    assert "needs_auth" not in result
    assert "not enabled" in result["error"]
    assert "console.cloud.google.com" in result["error"]
