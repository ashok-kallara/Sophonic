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


@patch("sophonic.gmail._service")
def test_unread_returns_summaries(mock_svc):
    from sophonic.gmail import unread

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


@patch("sophonic.gmail._service")
def test_unread_empty(mock_svc):
    from sophonic.gmail import unread

    svc = MagicMock()
    svc.users().messages().list().execute.return_value = {"messages": []}
    mock_svc.return_value = svc

    result = unread()
    assert result == []


@patch("sophonic.gmail._service")
def test_search_uses_query(mock_svc):
    from sophonic.gmail import search

    svc = MagicMock()
    svc.users().messages().list().execute.return_value = {"messages": []}
    mock_svc.return_value = svc

    search("from:boss@example.com is:unread")

    call_kwargs = svc.users().messages().list.call_args.kwargs
    assert call_kwargs["q"] == "from:boss@example.com is:unread"


def _mock_service_with_threads(my_email: str, list_thread_ids: list[str], threads: dict[str, dict]):
    svc = MagicMock()
    svc.users().getProfile().execute.return_value = {"emailAddress": my_email}
    svc.users().messages().list().execute.return_value = {
        "messages": [{"id": f"m{tid}", "threadId": tid} for tid in list_thread_ids]
    }

    def get_thread(userId, id, format, metadataHeaders):  # noqa: A002
        return MagicMock(execute=MagicMock(return_value=threads[id]))

    svc.users().threads().get.side_effect = get_thread
    return svc


def _thread_with_last_from(sender: str, subject: str = "Re: thing", snippet: str = "hi") -> dict:
    return {
        "messages": [
            {"payload": {"headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Sat, 03 May 2026 09:00:00 +0000"},
            ]}, "snippet": snippet},
        ]
    }


@patch("sophonic.gmail._service")
def test_followups_excludes_threads_i_replied_to_last(mock_svc):
    from sophonic.gmail import followups

    mock_svc.return_value = _mock_service_with_threads(
        my_email="me@example.com",
        list_thread_ids=["t1", "t2"],
        threads={
            "t1": _thread_with_last_from("alice@example.com", "Need input", "please review"),
            "t2": _thread_with_last_from("Me <me@example.com>", "Already answered"),
        },
    )

    result = followups(days=3)
    thread_ids = [i["thread_id"] for i in result["items"]]
    assert thread_ids == ["t1"]
    item = result["items"][0]
    assert item["subject"] == "Need input"
    assert item["from"] == "alice@example.com"
    assert item["snippet"] == "please review"
    assert item["link"] == "https://mail.google.com/mail/u/0/#inbox/t1"


@patch("sophonic.gmail._service")
def test_followups_dedupes_by_thread(mock_svc):
    from sophonic.gmail import followups

    svc = MagicMock()
    svc.users().getProfile().execute.return_value = {"emailAddress": "me@example.com"}
    svc.users().messages().list().execute.return_value = {
        "messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t1"}]
    }
    svc.users().threads().get.return_value.execute.return_value = _thread_with_last_from(
        "bob@example.com"
    )
    mock_svc.return_value = svc

    result = followups(days=3)
    assert len(result["items"]) == 1


@patch("sophonic.gmail._service")
def test_followups_respects_max_items(mock_svc):
    from sophonic.gmail import followups

    mock_svc.return_value = _mock_service_with_threads(
        my_email="me@example.com",
        list_thread_ids=["t1", "t2", "t3"],
        threads={
            tid: _thread_with_last_from("other@example.com") for tid in ("t1", "t2", "t3")
        },
    )

    result = followups(days=3, max_items=2)
    assert len(result["items"]) == 2


@patch("sophonic.gmail._service")
def test_followups_empty(mock_svc):
    from sophonic.gmail import followups

    svc = MagicMock()
    svc.users().getProfile().execute.return_value = {"emailAddress": "me@example.com"}
    svc.users().messages().list().execute.return_value = {"messages": []}
    mock_svc.return_value = svc

    result = followups()
    assert result == {"items": []}


@patch("sophonic.gmail._service")
def test_thread_returns_messages(mock_svc):
    from sophonic.gmail import thread

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
