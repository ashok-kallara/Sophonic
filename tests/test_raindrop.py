"""Tests for the Raindrop.io bookmark fetcher.

Every test uses the `tmp_config` fixture (redirects ~/.sophonic to a temp dir) so these
never depend on — or risk touching — a developer's real config.toml. The token itself is
supplied via the RAINDROP_TOKEN env var, which load_config() treats as authoritative.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import httpx


# ── helpers ───────────────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code: int = 200, json_data: Any = None,
                 headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.headers = headers or {}

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=MagicMock(),
                response=MagicMock(status_code=self.status_code),
            )


def _raindrop(id_: int, created: str, title: str = "Some Article", link: str = "https://example.com/a",
              domain: str = "example.com", tags: list[str] | None = None, type_: str = "article",
              collection_id: int = 0) -> dict[str, Any]:
    return {
        "_id": id_,
        "title": title,
        "excerpt": "excerpt text",
        "note": "",
        "link": link,
        "domain": domain,
        "type": type_,
        "tags": tags or [],
        "created": created,
        "lastUpdate": created,
        "collection": {"$id": collection_id},
        "important": False,
        "highlights": [],
    }


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def _set_token(monkeypatch, token: str | None) -> None:
    """Set (or clear) RAINDROP_TOKEN and bust load_config's cache. Requires the
    `tmp_config` fixture to already be active so this never touches real disk config."""
    from sophonic.config import load_config
    if token:
        monkeypatch.setenv("RAINDROP_TOKEN", token)
    else:
        monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    load_config.cache_clear()


# ── check_auth ──────────────────────────────────────────────────────────────

def test_check_auth_no_token_makes_no_network_call(tmp_config, monkeypatch):
    _set_token(monkeypatch, None)
    calls = MagicMock()
    monkeypatch.setattr(httpx, "get", calls)

    from sophonic.raindrop import check_auth
    result = check_auth()

    assert result == {"ok": False, "detail": "RAINDROP_TOKEN is not set"}
    calls.assert_not_called()


def test_check_auth_401_reports_invalid(tmp_config, monkeypatch):
    _set_token(monkeypatch, "bad-token")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(401))

    from sophonic.raindrop import check_auth
    result = check_auth()

    assert result["ok"] is False
    assert "401" in result["detail"]


def test_check_auth_ok(tmp_config, monkeypatch):
    _set_token(monkeypatch, "good-token")
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: _FakeResponse(200, {"user": {"email": "me@example.com"}})
    )

    from sophonic.raindrop import check_auth
    result = check_auth()

    assert result["ok"] is True
    assert "me@example.com" in result["detail"]


# ── bookmarks: auth ───────────────────────────────────────────────────────────

def test_bookmarks_no_token_needs_auth_no_network_call(tmp_config, monkeypatch):
    _set_token(monkeypatch, None)
    calls = MagicMock()
    monkeypatch.setattr(httpx, "get", calls)

    from sophonic.raindrop import bookmarks
    result = bookmarks()

    assert result["needs_auth"] is True
    assert "RAINDROP_TOKEN" in result["run"]
    calls.assert_not_called()


def test_bookmarks_401_needs_auth(tmp_config, monkeypatch):
    _set_token(monkeypatch, "bad-token")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(401))

    from sophonic.raindrop import bookmarks
    result = bookmarks()

    assert result["needs_auth"] is True


# ── bookmarks: pagination / date cutoff ───────────────────────────────────────

def test_bookmarks_stops_at_date_cutoff(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")

    page0 = [_raindrop(1, _iso(1)), _raindrop(2, _iso(5))]
    page1 = [_raindrop(3, _iso(40))]  # older than a 30-day window — must stop here

    def fake_get(url, headers=None, params=None, timeout=None):
        page = params.get("page", 0)
        return _FakeResponse(200, {"items": page0 if page == 0 else page1})

    monkeypatch.setattr(httpx, "get", fake_get)

    from sophonic.raindrop import bookmarks
    result = bookmarks(days=30)

    ids = {i["id"] for i in result["items"]}
    assert ids == {1, 2}
    assert result["truncated"] is False


def test_bookmarks_hits_page_cap_sets_truncated(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")

    def fake_get(url, headers=None, params=None, timeout=None):
        page = params.get("page", 0)
        # Always return a full, recent batch — pagination never finds an older item,
        # so the hard page cap is what stops it.
        return _FakeResponse(200, {"items": [_raindrop(100 + page, _iso(0))]})

    monkeypatch.setattr(httpx, "get", fake_get)

    from sophonic.raindrop import bookmarks
    result = bookmarks(days=3650)

    assert result["truncated"] is True


def test_bookmarks_empty_page_stops_pagination(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        page = params.get("page", 0)
        if page == 0:
            return _FakeResponse(200, {"items": [_raindrop(1, _iso(0))]})
        return _FakeResponse(200, {"items": []})

    monkeypatch.setattr(httpx, "get", fake_get)

    from sophonic.raindrop import bookmarks
    result = bookmarks(days=30)

    assert calls["n"] == 2  # page 0 (data), page 1 (empty, stop) — no cap hit
    assert result["truncated"] is False


# ── bookmarks: item normalization + filters ───────────────────────────────────

def test_bookmarks_normalizes_item_fields(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")
    raw = _raindrop(1, _iso(0), title="A Post", tags=["AI", "Infra"])
    raw["highlights"] = [{"text": "quote", "note": "why it matters"}]

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, {"items": [raw]}))

    from sophonic.raindrop import bookmarks
    item = bookmarks(days=30)["items"][0]

    assert item["title"] == "A Post"
    assert item["tags"] == ["AI", "Infra"]
    assert item["highlights"] == [{"text": "quote", "note": "why it matters"}]
    assert item["domain"] == "example.com"


def test_bookmarks_tag_filter_is_case_insensitive(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")
    items = [_raindrop(1, _iso(0), tags=["AI"]), _raindrop(2, _iso(0), tags=["cooking"])]

    def fake_get(url, headers=None, params=None, timeout=None):
        page = params.get("page", 0)
        return _FakeResponse(200, {"items": items if page == 0 else []})

    monkeypatch.setattr(httpx, "get", fake_get)

    from sophonic.raindrop import bookmarks
    result = bookmarks(days=30, tags=["ai"])

    assert [i["id"] for i in result["items"]] == [1]


def test_bookmarks_limit_honored(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")
    items = [_raindrop(i, _iso(0)) for i in range(5)]

    def fake_get(url, headers=None, params=None, timeout=None):
        page = params.get("page", 0)
        return _FakeResponse(200, {"items": items if page == 0 else []})

    monkeypatch.setattr(httpx, "get", fake_get)

    from sophonic.raindrop import bookmarks
    result = bookmarks(days=30, limit=2)

    assert result["count"] == 2


# ── bookmarks: collection resolution ──────────────────────────────────────────

def test_bookmarks_resolves_collection_by_name(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")
    seen_urls: list[str] = []

    def fake_get(url, headers=None, params=None, timeout=None):
        seen_urls.append(url)
        if url.endswith("/collections"):
            return _FakeResponse(200, {"items": [{"_id": 42, "title": "Reading", "count": 3}]})
        if url.endswith("/collections/childrens"):
            return _FakeResponse(200, {"items": []})
        return _FakeResponse(200, {"items": []})

    monkeypatch.setattr(httpx, "get", fake_get)

    from sophonic.raindrop import bookmarks
    bookmarks(days=30, collection="reading")  # case-insensitive

    assert any(url.endswith("/raindrops/42") for url in seen_urls)


def test_bookmarks_unknown_collection_returns_error_with_available(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/collections"):
            return _FakeResponse(200, {"items": [{"_id": 1, "title": "Reading", "count": 1}]})
        return _FakeResponse(200, {"items": []})

    monkeypatch.setattr(httpx, "get", fake_get)

    from sophonic.raindrop import bookmarks
    result = bookmarks(days=30, collection="NoSuchCollection")

    assert "error" in result
    assert result["available"] == ["Reading"]


# ── retry / backoff ────────────────────────────────────────────────────────────

def test_bookmarks_retries_on_429_then_succeeds(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")
    monkeypatch.setattr("time.sleep", lambda *_: None)

    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse(429, {}, headers={"Retry-After": "0"})
        page = params.get("page", 0)
        return _FakeResponse(200, {"items": [_raindrop(1, _iso(0))] if page == 0 else []})

    monkeypatch.setattr(httpx, "get", fake_get)

    from sophonic.raindrop import bookmarks
    result = bookmarks(days=30)

    assert result["count"] == 1
    assert calls["n"] >= 2


# ── collections() ─────────────────────────────────────────────────────────────

def test_collections_merges_root_and_nested(tmp_config, monkeypatch):
    _set_token(monkeypatch, "t")

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/collections"):
            return _FakeResponse(200, {"items": [{"_id": 1, "title": "Reading", "count": 2}]})
        if url.endswith("/collections/childrens"):
            return _FakeResponse(200, {"items": [
                {"_id": 2, "title": "Papers", "count": 1, "parent": {"$id": 1}},
            ]})
        return _FakeResponse(200, {"items": []})

    monkeypatch.setattr(httpx, "get", fake_get)

    from sophonic.raindrop import collections
    result = collections()

    paths = {c["id"]: c["path"] for c in result}
    assert paths[1] == "Reading"
    assert paths[2] == "Reading/Papers"


def test_collections_no_token_needs_auth(tmp_config, monkeypatch):
    _set_token(monkeypatch, None)

    from sophonic.raindrop import collections
    result = collections()

    assert result["needs_auth"] is True
