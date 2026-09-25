"""Gmail integration — read-only."""

from __future__ import annotations

import base64
import email as email_lib
import html
import re
from typing import Any

from sophonic.google_auth import get_credentials

# Docs/Sheets comment-mention notifications are handled by gdrive.py — surfacing them
# again as Gmail follow-ups would duplicate that, with a worse (unstructured) rendering
# of the same content.
_DOCS_COMMENT_SENDER = "comments-noreply@docs.google.com"

# Google Calendar sends invite/response emails from the *organizer's own address*, not
# a fixed notification sender, so the only reliable signal is its fixed subject-line
# templates (e.g. "Invitation: ...", "Accepted: ...", "Canceled event with note: ...").
# These are meeting logistics, not something to reply to — gcal.py is the source of
# truth for the meeting itself.
_INVITE_SUBJECT_RE = re.compile(
    r"^(invitation|updated invitation(?: with note)?|accepted|declined|tentative|"
    r"(?:canceled|cancelled) event(?: with note)?):\s",
    re.IGNORECASE,
)

_WHITESPACE_RE = re.compile(r"\s+")


def _clean(text: str, max_len: int = 200) -> str:
    """Decode HTML entities, collapse to a single line, and normalize quote chars.

    Gmail's snippet field is HTML-escaped (`&amp;`, `&#39;`, …), and a raw newline or
    embedded `"` in a header/snippet can corrupt the `- [ ] ` task line it's
    interpolated into (breaking the checkbox or truncating the item), so every field
    written into a task must pass through here first.
    """
    text = html.unescape(text or "")
    text = text.replace('"', "'").replace("“", "'").replace("”", "'")
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


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


def followups(days: int = 2, max_items: int = 20) -> dict[str, Any]:
    """Primary-inbox threads from the last `days` days whose most recent message isn't from me.

    Mirrors Slack's followups: search recent Primary-tab inbox mail (excluding meeting
    invites/responses and Docs/Sheets comment notifications, which are handled
    elsewhere), collapse to one entry per thread (dedup on thread id), and keep only
    threads where I haven't replied since — i.e. the thread's actual last message was
    sent by someone else. Every text field is passed through `_clean` so it can't
    corrupt the task line it ends up written into. Returns {"items": [...]}, each
    {thread_id, subject, from, date, snippet, link}.
    """
    from datetime import timedelta

    from sophonic.dates import today

    svc = _service()
    profile = svc.users().getProfile(userId="me").execute()
    my_email = (profile.get("emailAddress") or "").lower()

    since = (today() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = f"in:inbox category:primary after:{since} -in:chats -from:{_DOCS_COMMENT_SENDER}"
    result = svc.users().messages().list(userId="me", q=query, maxResults=100).execute()

    thread_ids: list[str] = []
    for item in result.get("messages", []):
        tid = item.get("threadId")
        if tid and tid not in thread_ids:
            thread_ids.append(tid)

    items: list[dict[str, Any]] = []
    for thread_id in thread_ids:
        if len(items) >= max_items:
            break
        thread_result = svc.users().threads().get(
            userId="me", id=thread_id, format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        msgs = thread_result.get("messages", [])
        if not msgs:
            continue
        last = msgs[-1]
        headers = {h["name"]: h["value"] for h in last.get("payload", {}).get("headers", [])}
        frm = headers.get("From", "")
        subject = headers.get("Subject", "")
        if my_email and my_email in frm.lower():
            continue  # I sent the last message — no follow-up needed
        if _DOCS_COMMENT_SENDER in frm.lower():
            continue  # belt-and-suspenders in case the query-level filter missed it
        if _INVITE_SUBJECT_RE.match(subject):
            continue  # Calendar invite/response — gcal is the source of truth for this
        items.append({
            "thread_id": thread_id,
            "subject": _clean(subject or "(no subject)", max_len=120),
            "from": _clean(frm),
            "date": headers.get("Date", ""),
            "snippet": _clean(last.get("snippet", "")),
            "link": f"https://mail.google.com/mail/u/0/#inbox/{thread_id}",
        })

    return {"items": items}


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
