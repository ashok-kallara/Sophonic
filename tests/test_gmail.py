"""Tests for Gmail integration (mocked API)."""

from unittest.mock import MagicMock, call, patch


def _make_message(id: str, subject: str, sender: str, snippet: str, thread_id: str = None) -> dict:
    return {
        "id": id,
        "threadId": thread_id or id,
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "Date", "value": "Sat, 03 May 2026 09:00:00 +0000"},
            ]
        },
        "snippet": snippet,
    }


def _mock_service_with_messages(messages: list[dict]):
    svc = MagicMock()
    # messages().list().execute returns ids
    svc.users().messages().list().execute.return_value = {
        "messages": [{"id": m["id"]} for m in messages]
    }
    # messages().get() returns full message; side_effect cycles through them
    get_mock = MagicMock()
    get_mock.execute.side_effect = messages
    svc.users().messages().get.return_value = get_mock
    return svc


@patch("sophonic.tools.gmail._service")
def test_unread_returns_summaries(mock_svc):
    from sophonic.tools.gmail import unread

    msgs = [
        _make_message("1", "Meeting notes", "alice@example.com", "Here are the notes..."),
        _make_message("2", "Lunch?", "bob@example.com", "Are you free for lunch?"),
    ]
    mock_svc.return_value = _mock_service_with_messages(msgs)

    result = unread(max=10)
    assert len(result) == 2
    assert result[0]["subject"] == "Meeting notes"
    assert result[0]["from"] == "alice@example.com"
    assert result[1]["subject"] == "Lunch?"


@patch("sophonic.tools.gmail._service")
def test_unread_empty(mock_svc):
    from sophonic.tools.gmail import unread

    svc = MagicMock()
    svc.users().messages().list().execute.return_value = {"messages": []}
    mock_svc.return_value = svc

    result = unread()
    assert result == []


@patch("sophonic.tools.gmail._service")
def test_search_uses_query(mock_svc):
    from sophonic.tools.gmail import search

    svc = MagicMock()
    svc.users().messages().list().execute.return_value = {"messages": []}
    mock_svc.return_value = svc

    search("from:boss@example.com is:unread")

    call_kwargs = svc.users().messages().list.call_args.kwargs
    assert call_kwargs["q"] == "from:boss@example.com is:unread"


@patch("sophonic.tools.gmail._service")
def test_thread_returns_messages(mock_svc):
    from sophonic.tools.gmail import thread

    svc = MagicMock()
    svc.users().threads().get().execute.return_value = {
        "messages": [
            _make_message("m1", "Re: Report", "bob@example.com", "LGTM"),
            _make_message("m2", "Re: Report", "alice@example.com", "Thanks"),
        ]
    }
    mock_svc.return_value = svc

    result = thread("thread-abc")
    assert result["thread_id"] == "thread-abc"
    assert len(result["messages"]) == 2
    assert result["messages"][0]["subject"] == "Re: Report"
