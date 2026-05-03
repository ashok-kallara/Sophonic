"""Slack web scraper — Playwright, persistent browser profile.

Uses stable Slack data-qa attributes where available, with fallbacks.
Selectors are centralised in _SELECTORS so they can be updated if Slack changes.
"""

from __future__ import annotations

from typing import Any

from akashic.browser import run_async

_NEEDS_AUTH = {"needs_auth": True, "run": "akashic auth slack"}

# Slack's DOM selectors — stable attributes first, class fallbacks last
_SELECTORS = {
    # The main channel sidebar container (wait on this to know the app is ready)
    "sidebar": '[data-qa="channel-sidebar"], .p-channel_sidebar, [aria-label="Sidebar"]',
    # Individual channel/DM rows in the sidebar
    "channel_item": '[data-qa="sidebar-channel-link"], [data-qa="channel_sidebar_name"]',
    # Badge indicating unread count
    "unread_badge": '[data-qa="badge"], .c-badge, [data-qa="unread-mention-badge"]',
    # Bold channel name (unread channels render their name bold)
    "unread_indicator": '.p-channel_sidebar__channel--unread, [aria-label*="unread"]',
    # Search bar trigger button
    "search_button": '[data-qa="top-nav-search"], [placeholder*="Search"], button[aria-label*="Search"]',
    # Search result items
    "search_results": '[data-qa="search-result-msg-pane-message"], .c-search__message',
}


def _is_auth_page(url: str) -> bool:
    return any(k in url for k in ("signin", "login", "sign-in", "/sso"))


async def _get_page(ctx, workspace_url: str):
    """Navigate to the workspace and wait for sidebar; return page or None if unauthed."""
    page = await ctx.new_page()
    await page.goto(workspace_url, timeout=30_000)
    try:
        await page.wait_for_selector(_SELECTORS["sidebar"], timeout=15_000)
    except Exception:
        pass  # sidebar may not match if auth wall shown

    if _is_auth_page(page.url):
        await page.close()
        return None
    return page


async def _unread_async(workspace_url: str) -> list[dict[str, Any]]:
    from akashic.browser import persistent_browser

    async with persistent_browser("slack") as ctx:
        page = await _get_page(ctx, workspace_url)
        if page is None:
            return [_NEEDS_AUTH]

        # Strategy 1: items with explicit unread aria-label or CSS class
        results: list[dict[str, Any]] = []
        unread_els = await page.query_selector_all(_SELECTORS["unread_indicator"])
        for el in unread_els[:30]:
            label = await el.get_attribute("aria-label") or await el.inner_text()
            href = await el.get_attribute("href") or ""
            name = label.replace(", unread", "").strip()
            if name:
                results.append({"channel": name, "link": href, "source": "aria"})

        # Strategy 2: any sidebar item that contains an unread badge
        if not results:
            items = await page.query_selector_all(_SELECTORS["channel_item"])
            for item in items[:60]:
                badge = await item.query_selector(_SELECTORS["unread_badge"])
                if badge:
                    name = (await item.inner_text()).strip().splitlines()[0]
                    href = await item.get_attribute("href") or ""
                    results.append({"channel": name, "link": href, "source": "badge"})

        return results or [{"message": "No unread items found"}]


async def _search_async(query: str, workspace_url: str) -> list[dict[str, Any]]:
    from akashic.browser import persistent_browser

    async with persistent_browser("slack") as ctx:
        page = await _get_page(ctx, workspace_url)
        if page is None:
            return [_NEEDS_AUTH]

        # Open search via keyboard shortcut (works in both old and new Slack)
        await page.keyboard.press("Meta+g")
        await page.wait_for_timeout(600)

        # Fallback: click the search button if shortcut didn't open it
        search_input = await page.query_selector('input[type="text"][placeholder*="search" i], [data-qa="search-input"]')
        if not search_input:
            btn = await page.query_selector(_SELECTORS["search_button"])
            if btn:
                await btn.click()
                await page.wait_for_timeout(600)
            search_input = await page.query_selector('input[type="text"]')

        if search_input:
            await search_input.fill(query)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)

        result_els = await page.query_selector_all(_SELECTORS["search_results"])
        out = []
        for r in result_els[:15]:
            text = (await r.inner_text()).strip()
            if text:
                out.append({"text": text[:200]})
        return out or [{"message": f"No results for: {query}"}]


def unread(workspace_url: str | None = None) -> list[dict[str, Any]]:
    """Return unread Slack channels/DMs. workspace_url defaults to config value."""
    from akashic.config import load_config
    url = workspace_url or load_config().slack.workspace_url
    return run_async(_unread_async(url))


def search(query: str, workspace_url: str | None = None) -> list[dict[str, Any]]:
    """Search Slack for a query string."""
    from akashic.config import load_config
    url = workspace_url or load_config().slack.workspace_url
    return run_async(_search_async(query, url))


TOOLS: dict[str, Any] = {
    "slack_unread": unread,
    "slack_search": search,
}
