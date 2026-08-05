"""Tests for the local-session Slack client (slack_local)."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from sophonic.tools import slack_local


# ── cookie decryption ────────────────────────────────────────────────────────────

def _encrypt(value: bytes, secret: bytes, prefix: bytes = b"") -> bytes:
    """Replicate Chromium macOS cookie encryption for a round-trip test."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = hashlib.pbkdf2_hmac("sha1", secret, b"saltysalt", 1003, 16)
    data = prefix + value
    pad = 16 - (len(data) % 16)
    data += bytes([pad]) * pad
    enc = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).encryptor()
    return b"v10" + enc.update(data) + enc.finalize()


def test_decrypt_cookie_round_trip():
    secret = b"test-safe-storage-key"
    blob = _encrypt(b"xoxd-abc123", secret)
    assert slack_local._decrypt_cookie(blob, secret) == "xoxd-abc123"


def test_decrypt_cookie_strips_domain_hash_prefix():
    secret = b"test-safe-storage-key"
    blob = _encrypt(b"xoxd-withprefix", secret, prefix=b"\x00" * 32)
    assert slack_local._decrypt_cookie(blob, secret) == "xoxd-withprefix"


# ── token acquisition ────────────────────────────────────────────────────────────

def test_derive_token_via_web(monkeypatch):
    html = 'var boot = {"api_token":"xoxc-DERIVED-123","other":1};'
    monkeypatch.setattr(slack_local.httpx, "get", lambda *a, **k: SimpleNamespace(text=html))
    assert slack_local._derive_token_via_web("xoxd-x", "acme.slack.com") == "xoxc-DERIVED-123"


def test_derive_token_returns_none_without_host():
    assert slack_local._derive_token_via_web("xoxd-x", "") is None


def test_leveldb_tokens_collects_all(tmp_path, monkeypatch):
    leveldb = tmp_path / "Local Storage" / "leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000005.log").write_bytes(b"\x00 xoxc-CURRENT-9 \x00 xoxc-STALE-1 \x00")
    monkeypatch.setattr(slack_local, "_slack_app_dir", lambda: tmp_path)
    tokens = slack_local._leveldb_tokens()
    assert "xoxc-CURRENT-9" in tokens
    assert "xoxc-STALE-1" in tokens


# ── unread / search mapping ──────────────────────────────────────────────────────

def _fake_api(monkeypatch, responses):
    """Patch _api with a dispatch keyed on (method, channel/user)."""
    def fake(method, params, token, d_cookie):
        key = method
        if method == "conversations.info":
            key = f"conversations.info:{params.get('channel')}"
        elif method == "users.info":
            key = f"users.info:{params.get('user')}"
        return responses[key]
    monkeypatch.setattr(slack_local, "_api", fake)


def test_unread_maps_channels_and_dms(monkeypatch):
    monkeypatch.setattr(slack_local, "_get_credentials", lambda: ("xoxc-t", "xoxd-c"))
    _fake_api(monkeypatch, {
        "client.counts": {
            "ok": True,
            "channels": [{"id": "C1", "has_unreads": True, "mention_count": 2}],
            "mpims": [],
            "ims": [{"id": "D1", "has_unreads": True, "mention_count": 0}],
        },
        "conversations.info:C1": {"ok": True, "channel": {"name": "general"}},
        "conversations.info:D1": {"ok": True, "channel": {"user": "U1"}},
        "users.info:U1": {"ok": True, "user": {"real_name": "Alice"}},
    })
    result = slack_local.unread()
    channels = {r["channel"] for r in result}
    assert "#general" in channels
    assert "@Alice" in channels


def test_search_maps_matches(monkeypatch):
    monkeypatch.setattr(slack_local, "_get_credentials", lambda: ("xoxc-t", "xoxd-c"))
    monkeypatch.setattr(slack_local, "_api", lambda *a, **k: {
        "ok": True,
        "messages": {"matches": [
            {"text": "seen the PR?", "channel": {"name": "eng"}, "username": "bob",
             "ts": "1.0", "permalink": "https://x/p"},
        ]},
    })
    result = slack_local.search("PR")
    assert result[0]["text"] == "seen the PR?"
    assert result[0]["channel"] == "eng"
    assert result[0]["permalink"] == "https://x/p"


def _fake_digest_api(monkeypatch, responses):
    """Patch _api with a dispatch that also keys conversations.history/getPermalink by channel."""
    def fake(method, params, token, d_cookie):
        key = method
        if method in ("conversations.info", "conversations.history", "chat.getPermalink"):
            key = f"{method}:{params.get('channel')}"
        elif method == "users.info":
            key = f"users.info:{params.get('user')}"
        return responses[key]
    monkeypatch.setattr(slack_local, "_api", fake)


def test_unread_digest_splits_actionable_and_informational(monkeypatch):
    monkeypatch.setattr(slack_local, "_get_credentials", lambda: ("xoxc-t", "xoxd-c"))
    _fake_digest_api(monkeypatch, {
        "client.counts": {
            "ok": True,
            "channels": [
                {"id": "C1", "has_unreads": True, "mention_count": 0},  # informational
                {"id": "C2", "has_unreads": True, "mention_count": 2},  # actionable (mention)
            ],
            "mpims": [],
            "ims": [{"id": "D1", "has_unreads": True, "mention_count": 0}],  # actionable (DM)
        },
        "conversations.info:C1": {"ok": True, "channel": {"name": "general"}},
        "conversations.info:C2": {"ok": True, "channel": {"name": "incidents"}},
        "conversations.info:D1": {"ok": True, "channel": {"user": "U1"}},
        "users.info:U1": {"ok": True, "user": {"real_name": "Alice"}},
        "users.info:U2": {"ok": True, "user": {"real_name": "Bob"}},
        "conversations.history:C1": {"ok": True, "messages": [
            {"user": "U2", "text": "newer", "ts": "2"},
            {"user": "U2", "text": "older", "ts": "1"},
        ]},
        "conversations.history:C2": {"ok": True, "messages": [{"user": "U2", "text": "prod is down", "ts": "5"}]},
        "conversations.history:D1": {"ok": True, "messages": [{"user": "U1", "text": "ping you", "ts": "9"}]},
        "chat.getPermalink:C1": {"ok": True, "permalink": "https://slack/C1"},
        "chat.getPermalink:C2": {"ok": True, "permalink": "https://slack/C2"},
        "chat.getPermalink:D1": {"ok": True, "permalink": "https://slack/D1"},
    })

    digest = slack_local.unread_digest()
    info_channels = {e["channel"] for e in digest["informational"]}
    action_channels = {e["channel"] for e in digest["actionable"]}

    assert info_channels == {"#general"}
    assert action_channels == {"#incidents", "@Alice"}  # mention channel + DM

    general = next(e for e in digest["informational"] if e["channel"] == "#general")
    assert [m["text"] for m in general["messages"]] == ["older", "newer"]  # chronological
    assert general["messages"][0]["user"] == "Bob"                         # user resolved
    assert general["latest"] == "newer"
    assert general["permalink"] == "https://slack/C1"


def test_unread_digest_needs_auth(monkeypatch):
    def raise_auth():
        raise slack_local.SlackAuthError("no cookie")
    monkeypatch.setattr(slack_local, "_get_credentials", raise_auth)
    result = slack_local.unread_digest()
    assert result["needs_auth"] is True


def test_unread_needs_auth_when_no_session(monkeypatch):
    def raise_auth():
        raise slack_local.SlackAuthError("no cookie")
    monkeypatch.setattr(slack_local, "_get_credentials", raise_auth)
    result = slack_local.unread()
    assert result[0]["needs_auth"] is True


def test_search_needs_auth_when_no_session(monkeypatch):
    def raise_auth():
        raise slack_local.SlackAuthError("no cookie")
    monkeypatch.setattr(slack_local, "_get_credentials", raise_auth)
    result = slack_local.search("x")
    assert result[0]["needs_auth"] is True
