"""Raindrop.io integration — read-only bookmark fetcher.

Reads saved bookmarks (and collections) from the user's Raindrop.io account via a
permanent "test token" (Settings → Integrations → your app → Create test token — no
OAuth flow needed for single-user use). Auth failures are returned as data
(`{"needs_auth": ...}`), never raised — the script boundary must always emit valid JSON.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any

import httpx

_API = "https://api.raindrop.io/rest/v1"
_TIMEOUT = 20.0
_MAX_RETRIES = 3
_MAX_PAGES = 20  # hard cap on pagination — protects against a runaway/huge account
_PER_PAGE = 50

_NEEDS_AUTH = {
    "needs_auth": True,
    "run": "uv run python scripts/config.py set-secret RAINDROP_TOKEN --stdin",
    "detail": (
        "Raindrop.io token is missing or invalid. Create a test token at "
        "raindrop.io/settings/integrations (+ Create new app → Create test token) and "
        "paste it into "
        "`uv run python scripts/config.py set-secret RAINDROP_TOKEN --stdin`."
    ),
}


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _get(path: str, token: str, params: dict[str, Any] | None = None) -> httpx.Response:
    """GET with bounded retry on 429/5xx, honoring Retry-After when present."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = httpx.get(
                f"{_API}{path}", headers=_headers(token), params=params, timeout=_TIMEOUT
            )
        except httpx.RequestError as exc:
            last_exc = exc
            time.sleep(2**attempt)
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == _MAX_RETRIES - 1:
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else 2**attempt
            time.sleep(delay)
            continue

        return resp

    # Only reachable after exhausting retries on a RequestError (network failure).
    raise last_exc  # type: ignore[misc]


def check_auth() -> dict[str, Any]:
    """Probe token validity via GET /user. Returns {ok, detail}."""
    from sophonic.config import load_config

    token = load_config().raindrop.token
    if not token:
        return {"ok": False, "detail": "RAINDROP_TOKEN is not set"}
    try:
        resp = _get("/user", token)
    except httpx.RequestError as exc:
        return {"ok": False, "detail": f"Could not reach Raindrop.io: {exc}"}
    if resp.status_code == 401:
        return {"ok": False, "detail": "Raindrop.io rejected the token (401)"}
    resp.raise_for_status()
    email = (resp.json().get("user") or {}).get("email", "")
    return {"ok": True, "detail": f"authenticated{' as ' + email if email else ''}"}


def collections() -> list[dict[str, Any]] | dict[str, Any]:
    """List collections (top-level + nested). Returns [{id, title, path, count}]."""
    from sophonic.config import load_config

    token = load_config().raindrop.token
    if not token:
        return _NEEDS_AUTH

    try:
        root = _get("/collections", token)
        child = _get("/collections/childrens", token)
    except httpx.RequestError as exc:
        return {"error": f"Could not reach Raindrop.io: {exc}"}

    if root.status_code == 401 or child.status_code == 401:
        return _NEEDS_AUTH
    root.raise_for_status()
    child.raise_for_status()

    by_id: dict[int, dict[str, Any]] = {}
    paths: dict[int, str] = {}
    for item in root.json().get("items", []):
        by_id[item["_id"]] = item
        paths[item["_id"]] = item["title"]
    for item in child.json().get("items", []):
        by_id[item["_id"]] = item
        parent_id = (item.get("parent") or {}).get("$id")
        parent_path = paths.get(parent_id, "")
        paths[item["_id"]] = f"{parent_path}/{item['title']}" if parent_path else item["title"]

    return [
        {
            "id": cid,
            "title": item["title"],
            "path": paths.get(cid, item["title"]),
            "count": item.get("count", 0),
        }
        for cid, item in sorted(by_id.items(), key=lambda kv: paths.get(kv[0], ""))
    ]


def _resolve_collection(name_or_id: str, token: str) -> int | dict[str, Any]:
    """Accept a collection id or a case-insensitive name/path; return its id.

    Returns an {"error", "available"} dict if a name doesn't match anything.
    """
    stripped = name_or_id.strip()
    if not stripped:
        return 0
    if stripped.lstrip("-").isdigit():
        return int(stripped)

    found = collections()
    if isinstance(found, dict):  # needs_auth / error — propagate
        return found
    lowered = stripped.lower()
    for c in found:
        if c["title"].lower() == lowered or c["path"].lower() == lowered:
            return c["id"]
    return {"error": f"No Raindrop collection matches {name_or_id!r}",
            "available": [c["path"] for c in found]}


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    collection = raw.get("collection") or {}
    return {
        "id": raw.get("_id"),
        "title": raw.get("title") or "",
        "excerpt": raw.get("excerpt") or "",
        "note": raw.get("note") or "",
        "link": raw.get("link") or "",
        "domain": raw.get("domain") or "",
        "type": raw.get("type") or "link",
        "tags": raw.get("tags") or [],
        "created": raw.get("created"),
        "last_update": raw.get("lastUpdate"),
        "collection_id": collection.get("$id"),
        "important": bool(raw.get("important")),
        "highlights": [
            {"text": h.get("text", ""), "note": h.get("note", "")}
            for h in (raw.get("highlights") or [])
        ],
    }


def bookmarks(
    days: int = 30,
    since: date | None = None,
    until: date | None = None,
    collection: str | None = None,
    tags: list[str] | None = None,
    search: str | None = None,
    item_type: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """List bookmarks in a date window, newest first.

    Raindrop's search syntax for date filters isn't reliably documented, so this
    fetches sorted-by-created pages and stops client-side once items fall before the
    cutoff — the safe, version-proof approach.
    """
    from sophonic.config import load_config

    cfg = load_config().raindrop
    token = cfg.token
    if not token:
        return _NEEDS_AUTH

    until_d = until or date.today()
    since_d = since or (until_d - timedelta(days=days))

    coll_ref = collection or cfg.default_collection
    collection_id = 0
    if coll_ref:
        resolved = _resolve_collection(coll_ref, token)
        if isinstance(resolved, dict):
            return resolved
        collection_id = resolved

    params: dict[str, Any] = {"sort": "-created", "perpage": _PER_PAGE}
    if search:
        params["search"] = search

    items: list[dict[str, Any]] = []
    truncated = False
    try:
        for page in range(_MAX_PAGES):
            resp = _get(f"/raindrops/{collection_id}", token, {**params, "page": page})
            if resp.status_code == 401:
                return _NEEDS_AUTH
            resp.raise_for_status()
            batch = resp.json().get("items", [])
            if not batch:
                break

            stop = False
            for raw in batch:
                item = _normalize(raw)
                created = _parse_ts(item["created"])
                if created is not None and created.date() < since_d:
                    stop = True
                    break
                if created is not None and created.date() > until_d:
                    continue
                items.append(item)
            if stop:
                break
            if page == _MAX_PAGES - 1:
                truncated = True
    except httpx.RequestError as exc:
        return {"error": f"Could not reach Raindrop.io: {exc}"}

    if tags:
        wanted = {t.lower() for t in tags}
        items = [i for i in items if wanted & {t.lower() for t in i["tags"]}]
    if item_type:
        items = [i for i in items if i["type"] == item_type]
    if limit:
        items = items[:limit]

    return {
        "range": {"since": since_d.isoformat(), "until": until_d.isoformat()},
        "collection": coll_ref or "all",
        "count": len(items),
        "truncated": truncated,
        "items": items,
    }


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
