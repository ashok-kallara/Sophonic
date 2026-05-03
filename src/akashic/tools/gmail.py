"""Gmail integration — read-only."""

from __future__ import annotations

import base64
import email as email_lib
from typing import Any

from akashic.google_auth import get_credentials


def _service():
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=get_credentials())


def _decode_body(payload: dict) -> str:
    """Extract plain-text body from a Gmail message payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        text = _decode_body(part)
        if text:
            return text
    return ""


def _message_summary(msg: dict) -> dict[str, Any]:
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "subject": headers.get("Subject", "(no subject)"),
        "from": headers.get("From", ""),
        "date": headers.get("Date", ""),
        "snippet": msg.get("snippet", ""),
    }


def unread(max: int = 20) -> list[dict[str, Any]]:
    """Return the most recent unread messages."""
    svc = _service()
    result = svc.users().messages().list(
        userId="me", q="is:unread", maxResults=max
    ).execute()
    messages = []
    for item in result.get("messages", []):
        msg = svc.users().messages().get(userId="me", id=item["id"], format="metadata").execute()
        messages.append(_message_summary(msg))
    return messages


def search(query: str, max: int = 20) -> list[dict[str, Any]]:
    """Search Gmail and return matching message summaries."""
    svc = _service()
    result = svc.users().messages().list(
        userId="me", q=query, maxResults=max
    ).execute()
    messages = []
    for item in result.get("messages", []):
        msg = svc.users().messages().get(userId="me", id=item["id"], format="metadata").execute()
        messages.append(_message_summary(msg))
    return messages


def thread(thread_id: str) -> dict[str, Any]:
    """Return all messages in a thread with body text."""
    svc = _service()
    result = svc.users().threads().get(userId="me", id=thread_id).execute()
    msgs = []
    for msg in result.get("messages", []):
        summary = _message_summary(msg)
        summary["body"] = _decode_body(msg.get("payload", {}))
        msgs.append(summary)
    return {"thread_id": thread_id, "messages": msgs}


TOOLS: dict[str, Any] = {
    "gmail_unread": unread,
    "gmail_search": search,
    "gmail_thread": thread,
}
