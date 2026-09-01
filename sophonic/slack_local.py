"""Slack access via the desktop app's local session — no browser automation.

Reads the `d` session cookie from the Slack desktop app's encrypted cookie store
(decrypted with the macOS Keychain "Slack Safe Storage" key), obtains the workspace
`xoxc` token, and calls Slack's Web API directly. Works headless and from the plugin.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import httpx

_NEEDS_AUTH = {"needs_auth": True, "run": "uv run python scripts/auth.py slack"}
_XOXC_RE = re.compile(rb"xoxc-[0-9A-Za-z-]+")
_API_TOKEN_RE = re.compile(r'"api_token":"(xoxc-[^"]+)"')


class SlackAuthError(Exception):
    """Raised when a usable Slack session cannot be assembled from the local app."""


def _slack_app_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Slack"


# ── cookie (d) ──────────────────────────────────────────────────────────────────

def _keychain_secret() -> bytes:
    """Return the Chromium 'Slack Safe Storage' key from the login Keychain."""
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Slack Safe Storage", "-a", "Slack"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise SlackAuthError(
            "Could not read the 'Slack Safe Storage' key from your Keychain "
            "(access denied or missing). Approve the Keychain prompt and retry."
        )
    return result.stdout.strip().encode("utf-8")


def _decrypt_cookie(encrypted: bytes, secret: bytes) -> str:
    """Decrypt a Chromium macOS cookie value (AES-128-CBC, PBKDF2 'saltysalt')."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if encrypted[:3] in (b"v10", b"v11"):
        encrypted = encrypted[3:]
    key = hashlib.pbkdf2_hmac("sha1", secret, b"saltysalt", 1003, 16)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    plaintext = decryptor.update(encrypted) + decryptor.finalize()

    if plaintext:  # strip PKCS7 padding
        pad = plaintext[-1]
        if 1 <= pad <= 16:
            plaintext = plaintext[:-pad]
    if not plaintext.startswith(b"xoxd-"):
        # newer Chromium prepends a 32-byte SHA256(host) hash to the value
        if plaintext[32:].startswith(b"xoxd-"):
            plaintext = plaintext[32:]
    return plaintext.decode("utf-8", "replace")


def _read_d_cookie() -> str:
    """Decrypt and return the Slack `d` session cookie (xoxd-…) from the desktop app."""
    db = _slack_app_dir() / "Cookies"
    if not db.exists():
        raise SlackAuthError(
            "Slack desktop app cookie store not found — install and sign in to the Slack app."
        )
    # immutable read-only open works even while Slack is running
    con = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    try:
        row = con.execute(
            "SELECT encrypted_value FROM cookies "
            "WHERE name='d' AND host_key LIKE '%slack.com%' "
            "ORDER BY LENGTH(encrypted_value) DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise SlackAuthError("No Slack `d` cookie found — sign in to the Slack desktop app.")
    return _decrypt_cookie(row[0], _keychain_secret())


# ── token (xoxc) ─────────────────────────────────────────────────────────────────

def _leveldb_tokens() -> list[str]:
    """All unique xoxc tokens in the Slack app's localStorage leveldb.

    There can be several (current + stale from workspace switches); the caller
    validates each with auth.test and keeps the one that works.
    """
    leveldb = _slack_app_dir() / "Local Storage" / "leveldb"
    if not leveldb.exists():
        return []
    seen: list[str] = []
    for path in sorted(leveldb.glob("*.log")) + sorted(leveldb.glob("*.ldb")):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        for match in _XOXC_RE.findall(data):
            token = match.decode("ascii", "replace")
            if token not in seen:
                seen.append(token)
    return seen


def _derive_token_via_web(d_cookie: str, host: str) -> str | None:
    """Fetch the workspace HTML with the `d` cookie and read the embedded api_token."""
    if not host:
        return None
    try:
        resp = httpx.get(
            f"https://{host}/",
            headers={"Cookie": f"d={d_cookie}"},
            timeout=15,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        return None
    match = _API_TOKEN_RE.search(resp.text)
    return match.group(1) if match else None


def _cache_token(token: str) -> None:
    try:
        from sophonic import config_io
        config_io.set_secret("SLACK_XOXC_TOKEN", token)
    except Exception:
        pass  # caching is best-effort; the token still works this run


def _get_credentials() -> tuple[str, str]:
    """Return (xoxc_token, d_cookie), validating via auth.test. Raises SlackAuthError."""
    from sophonic.config import load_config

    d_cookie = _read_d_cookie()
    host = load_config().slack.workspace_host

    cached = os.environ.get("SLACK_XOXC_TOKEN")
    if cached and _auth_ok(cached, d_cookie):
        return cached, d_cookie

    candidates = _leveldb_tokens()
    web = _derive_token_via_web(d_cookie, host)
    if web:
        candidates.append(web)
    for candidate in candidates:
        if _auth_ok(candidate, d_cookie):
            _cache_token(candidate)
            return candidate, d_cookie

    raise SlackAuthError(
        "Could not obtain a valid Slack token. Set `slack.workspace_host` "
        "(e.g. your-org.enterprise.slack.com) or the SLACK_XOXC_TOKEN secret."
    )


# ── Web API ──────────────────────────────────────────────────────────────────────

def _api(method: str, params: dict[str, Any], token: str, d_cookie: str) -> dict[str, Any]:
    resp = httpx.post(
        f"https://slack.com/api/{method}",
        headers={"Authorization": f"Bearer {token}", "Cookie": f"d={d_cookie}"},
        data=params or {},
        timeout=30,
    )
    return resp.json()


def _auth_ok(token: str, d_cookie: str) -> bool:
    try:
        return bool(_api("auth.test", {}, token, d_cookie).get("ok"))
    except Exception:
        return False


def _resolve_name(cid: str, kind: str, token: str, d_cookie: str) -> str:
    info = _api("conversations.info", {"channel": cid}, token, d_cookie)
    channel = info.get("channel", {}) if info.get("ok") else {}
    if kind == "im":
        uid = channel.get("user")
        if uid:
            user = _api("users.info", {"user": uid}, token, d_cookie)
            if user.get("ok"):
                u = user["user"]
                return "@" + (u.get("real_name") or u.get("name") or uid)
        return "@dm"
    name = channel.get("name")
    return f"#{name}" if name else (cid or "unknown")


# ── public tools ─────────────────────────────────────────────────────────────────

def unread() -> list[dict[str, Any]]:
    """Return unread Slack channels, group DMs, and DMs (via the client.counts API)."""
    try:
        token, d_cookie = _get_credentials()
    except SlackAuthError as exc:
        return [{**_NEEDS_AUTH, "detail": str(exc)}]

    counts = _api("client.counts", {}, token, d_cookie)
    if not counts.get("ok"):
        if counts.get("error") == "invalid_auth":
            return [_NEEDS_AUTH]
        return [{"error": counts.get("error", "unknown")}]

    out: list[dict[str, Any]] = []
    for kind, key in (("channel", "channels"), ("mpim", "mpims"), ("im", "ims")):
        for item in counts.get(key, []):
            if not item.get("has_unreads"):
                continue
            cid = item.get("id", "")
            out.append({
                "channel": _resolve_name(cid, kind, token, d_cookie),
                "type": kind,
                "mentions": item.get("mention_count", 0),
                "id": cid,
            })
            if len(out) >= 40:
                return out
    return out or [{"message": "No unread items"}]


def _user_name(uid: str, token: str, d_cookie: str, cache: dict[str, str]) -> str:
    """Resolve a Slack user id to a display name, memoized per call."""
    if not uid:
        return ""
    if uid in cache:
        return cache[uid]
    info = _api("users.info", {"user": uid}, token, d_cookie)
    name = uid
    if info.get("ok"):
        u = info["user"]
        name = u.get("real_name") or u.get("name") or uid
    cache[uid] = name
    return name


def _conversation_digest(
    cid: str, kind: str, mentions: int, last_read: str | None,
    per_channel: int, token: str, d_cookie: str, cache: dict[str, str],
) -> dict[str, Any]:
    """Recent message content + metadata for one unread conversation."""
    channel = _resolve_name(cid, kind, token, d_cookie)
    params: dict[str, Any] = {"channel": cid, "limit": per_channel}
    if last_read:
        params["oldest"] = last_read
    hist = _api("conversations.history", params, token, d_cookie)
    raw = hist.get("messages", []) if hist.get("ok") else []

    msgs: list[dict[str, Any]] = []
    for m in reversed(raw):  # history is newest-first; present chronologically
        if m.get("subtype"):  # skip joins/leaves/other system messages
            continue
        msgs.append({
            "user": _user_name(m.get("user", ""), token, d_cookie, cache),
            "text": (m.get("text") or "")[:500],
            "ts": m.get("ts", ""),
        })

    permalink = _permalink(cid, msgs[-1]["ts"], token, d_cookie) if msgs else ""

    return {
        "channel": channel,
        "type": kind,
        "mentions": mentions,
        "latest": msgs[-1]["text"] if msgs else "",
        "permalink": permalink,
        "messages": msgs,
    }


def unread_digest(per_channel: int = 8, max_channels: int = 25) -> dict[str, Any]:
    """Unread Slack conversations with recent content, split into actionable vs informational.

    Actionable = DMs or conversations with @-mentions (likely need a reply). Informational =
    other unread channels. Returns {"actionable": [...], "informational": [...]}, each entry
    carrying recent messages, the latest snippet, mention count, and a best-effort permalink.
    """
    try:
        token, d_cookie = _get_credentials()
    except SlackAuthError as exc:
        return {**_NEEDS_AUTH, "detail": str(exc)}

    counts = _api("client.counts", {}, token, d_cookie)
    if not counts.get("ok"):
        if counts.get("error") == "invalid_auth":
            return dict(_NEEDS_AUTH)
        return {"error": counts.get("error", "unknown")}

    cache: dict[str, str] = {}
    actionable: list[dict[str, Any]] = []
    informational: list[dict[str, Any]] = []
    processed = 0

    for kind, key in (("channel", "channels"), ("mpim", "mpims"), ("im", "ims")):
        for item in counts.get(key, []):
            if not item.get("has_unreads"):
                continue
            if processed >= max_channels:
                break
            processed += 1
            mentions = item.get("mention_count", 0)
            entry = _conversation_digest(
                item.get("id", ""), kind, mentions, item.get("last_read"),
                per_channel, token, d_cookie, cache,
            )
            (actionable if (kind == "im" or mentions > 0) else informational).append(entry)

    return {"actionable": actionable, "informational": informational}


_THREAD_TS_RE = re.compile(r"thread_ts=([0-9.]+)")


def _is_bot(match: dict[str, Any]) -> bool:
    """Fast-path: message flagged as bot-authored on the match itself."""
    return bool(match.get("bot_id")) or match.get("subtype") == "bot_message"


def _is_bot_user(uid: str, token: str, d_cookie: str, cache: dict[str, bool]) -> bool:
    """True if the author is a bot/app user (e.g. Google Calendar/Drive) — via users.info.

    App-DM search matches don't set bot_id, so the reliable signal is the user's is_bot flag.
    """
    if not uid:
        return False
    if uid in cache:
        return cache[uid]
    info = _api("users.info", {"user": uid}, token, d_cookie)
    is_bot = bool(info.get("user", {}).get("is_bot")) if info.get("ok") else False
    cache[uid] = is_bot
    return is_bot


def _thread_ts(match: dict[str, Any]) -> str | None:
    """Extract a thread_ts from a search match (present in the permalink when threaded)."""
    pl = match.get("permalink") or ""
    m = _THREAD_TS_RE.search(pl)
    return m.group(1) if m else None


def _responded_after(channel: str, ts: str, thread_ts: str | None, my_uid: str,
                     token: str, d_cookie: str) -> bool:
    """True if I authored a message after `ts` in the thread (if any) or the channel."""
    if thread_ts:
        r = _api("conversations.replies", {"channel": channel, "ts": thread_ts, "limit": 50}, token, d_cookie)
    else:
        r = _api("conversations.history", {"channel": channel, "oldest": ts, "limit": 30}, token, d_cookie)
    msgs = r.get("messages", []) if r.get("ok") else []
    try:
        after = float(ts)
    except ValueError:
        return False
    for m in msgs:
        if m.get("user") == my_uid:
            try:
                if float(m.get("ts", "0")) > after:
                    return True
            except ValueError:
                continue
    return False


def _label_for(channel_obj: dict[str, Any] | None, cid: str, token: str, d_cookie: str) -> str:
    """Human label for a conversation: '#channel' or '@Name' (resolving DMs)."""
    if channel_obj is not None:
        if channel_obj.get("is_im"):
            return _resolve_name(channel_obj.get("id", "") or cid, "im", token, d_cookie)
        name = channel_obj.get("name")
        return f"#{name}" if name else (channel_obj.get("id", "") or cid)
    kind = "im" if cid.startswith("D") else "channel"
    return _resolve_name(cid, kind, token, d_cookie)


def _message_text(cid: str, ts: str, token: str, d_cookie: str) -> str:
    r = _api("conversations.history",
             {"channel": cid, "latest": ts, "oldest": ts, "inclusive": True, "limit": 1},
             token, d_cookie)
    msgs = r.get("messages", []) if r.get("ok") else []
    return (msgs[0].get("text") if msgs else "") or ""


def _team_domain(token: str, d_cookie: str) -> str:
    """Workspace subdomain (e.g. "omada") for hand-building permalinks."""
    info = _api("team.info", {}, token, d_cookie)
    return ((info.get("team") or {}).get("domain") or "") if info.get("ok") else ""


def _permalink(cid: str, ts: str, token: str, d_cookie: str) -> str:
    """Permalink for a channel+ts.

    Falls back to a hand-built `/archives/<channel>/p<ts>` URL when
    chat.getPermalink itself fails — some Enterprise Grid tokens get
    `enterprise_is_restricted` on that endpoint even though the message is
    otherwise fully readable.
    """
    pl = _api("chat.getPermalink", {"channel": cid, "message_ts": ts}, token, d_cookie)
    if pl.get("ok"):
        return pl.get("permalink", "")
    domain = _team_domain(token, d_cookie)
    if not domain or not cid or not ts:
        return ""
    return f"https://{domain}.slack.com/archives/{cid}/p{ts.replace('.', '')}"


def followups(days: int = 2, max_items: int = 20) -> dict[str, Any]:
    """Slack items that likely need action, beyond just unread.

    Finds, from the last `days` days: (1) channel messages that @-mention me — read or
    not — where I have not since replied; (2) DMs to me I have not replied to; and
    (3) messages I saved for "Later" (uncompleted). Returns {"items": [...]}, each
    {kind: mention|dm|later, channel, from, text, ts, permalink}. "Responded" means I
    authored a later message in the thread (if threaded) or the channel.
    """
    from datetime import timedelta

    from sophonic.dates import today

    try:
        token, d_cookie = _get_credentials()
    except SlackAuthError as exc:
        return {**_NEEDS_AUTH, "detail": str(exc)}

    me = _api("auth.test", {}, token, d_cookie)
    if not me.get("ok"):
        return dict(_NEEDS_AUTH) if me.get("error") == "invalid_auth" else {"error": me.get("error", "unknown")}
    my_uid, handle = me.get("user_id", ""), me.get("user", "")
    since = (today() - timedelta(days=days)).isoformat()

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    bot_cache: dict[str, bool] = {}

    def add(kind: str, cid: str, label: str, ts: str, text: str, frm: str, permalink: str,
            key: tuple[str, ...]) -> None:
        # `key` collapses noise: one item per DM conversation and per mention thread,
        # but each saved-for-later message is kept distinct. Search returns newest-first,
        # so the first (most recent) unanswered message per conversation/thread wins.
        if key in seen:
            return
        seen.add(key)
        items.append({
            "kind": kind, "channel": label, "from": frm,
            "text": (text or "").replace("\n", " ").strip()[:200],
            "ts": ts, "permalink": permalink,
        })

    def _search(query: str) -> list[dict[str, Any]]:
        r = _api("search.messages", {"query": query, "count": 30}, token, d_cookie)
        return r.get("messages", {}).get("matches", []) if r.get("ok") else []

    # 1) Channel @-mentions of me (read or unread) with no reply from me since.
    if handle:
        for m in _search(f"@{handle} after:{since}"):
            if len(items) >= max_items:
                break
            if m.get("user") == my_uid or _is_bot(m) or _is_bot_user(m.get("user", ""), token, d_cookie, bot_cache):
                continue
            ch = m.get("channel", {})
            cid, ts = ch.get("id", ""), m.get("ts", "")
            tts = _thread_ts(m)
            if _responded_after(cid, ts, tts, my_uid, token, d_cookie):
                continue
            add("mention", cid, _label_for(ch, cid, token, d_cookie), ts,
                m.get("text", ""), m.get("username", ""), m.get("permalink", ""),
                key=("mention", cid, tts or ts))  # one per thread

    # 2) DMs to me with no reply from me since.
    if handle:
        for m in _search(f"to:@{handle} after:{since}"):
            if len(items) >= max_items:
                break
            if m.get("user") == my_uid or _is_bot(m) or _is_bot_user(m.get("user", ""), token, d_cookie, bot_cache):
                continue
            ch = m.get("channel", {})
            cid, ts = ch.get("id", ""), m.get("ts", "")
            if _responded_after(cid, ts, None, my_uid, token, d_cookie):
                continue
            add("dm", cid, _label_for(ch, cid, token, d_cookie), ts,
                m.get("text", ""), m.get("username", ""), m.get("permalink", ""),
                key=("dm", cid))  # one per DM conversation

    # 3) Saved for "Later" (uncompleted, not archived).
    sv = _api("saved.list", {}, token, d_cookie)
    if sv.get("ok"):
        for it in sv.get("saved_items", []):
            if len(items) >= max_items:
                break
            if it.get("item_type") != "message" or it.get("is_archived") or it.get("state") == "completed":
                continue
            cid, ts = it.get("item_id", ""), it.get("ts", "")
            add("later", cid, _label_for(None, cid, token, d_cookie), ts,
                _message_text(cid, ts, token, d_cookie), "", _permalink(cid, ts, token, d_cookie),
                key=("later", cid, ts))  # each saved message kept distinct

    return {"items": items[:max_items]}


def search(query: str) -> list[dict[str, Any]]:
    """Search Slack messages (via the search.messages API)."""
    try:
        token, d_cookie = _get_credentials()
    except SlackAuthError as exc:
        return [{**_NEEDS_AUTH, "detail": str(exc)}]

    res = _api("search.messages", {"query": query, "count": 20}, token, d_cookie)
    if not res.get("ok"):
        if res.get("error") == "invalid_auth":
            return [_NEEDS_AUTH]
        return [{"error": res.get("error", "unknown")}]

    matches = res.get("messages", {}).get("matches", [])
    out = [
        {
            "text": (m.get("text") or "")[:300],
            "channel": (m.get("channel") or {}).get("name", ""),
            "user": m.get("username", ""),
            "ts": m.get("ts", ""),
            "permalink": m.get("permalink", ""),
        }
        for m in matches[:20]
    ]
    return out or [{"message": f"No results for: {query}"}]
