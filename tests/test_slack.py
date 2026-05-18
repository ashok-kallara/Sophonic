"""Tests for Slack scraper (mocked Playwright)."""

from unittest.mock import AsyncMock, patch

import pytest


def _mock_page(url="https://app.slack.com", unread_labels=None, search_texts=None):
    page = AsyncMock()
    page.url = url
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.goto = AsyncMock()
    page.keyboard = AsyncMock()

    if unread_labels:
        els = []
        for label in unread_labels:
            el = AsyncMock()
            el.get_attribute = AsyncMock(
                side_effect=lambda attr, label=label: label if attr == "aria-label" else ""
            )
            el.inner_text = AsyncMock(return_value=label)
            els.append(el)
        page.query_selector_all = AsyncMock(return_value=els)
        page.query_selector = AsyncMock(return_value=None)
    elif search_texts:
        els = []
        for text in search_texts:
            el = AsyncMock()
            el.inner_text = AsyncMock(return_value=text)
            els.append(el)
        page.query_selector_all = AsyncMock(return_value=els)
        page.query_selector = AsyncMock(
            return_value=AsyncMock(fill=AsyncMock(), get_attribute=AsyncMock(return_value=""))
        )
    else:
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=None)

    return page


def _ctx_with_page(page):
    ctx = AsyncMock()
    ctx.new_page = AsyncMock(return_value=page)
    return ctx


@pytest.mark.asyncio
async def test_unread_returns_channels():
    from sophonic.tools.slack_web import _unread_async

    page = _mock_page(unread_labels=["#general, unread", "#engineering, unread"])

    with patch("sophonic.browser.persistent_browser") as mock_pb:
        mock_pb.return_value.__aenter__ = AsyncMock(return_value=_ctx_with_page(page))
        mock_pb.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _unread_async("https://app.slack.com")

    assert any("#general" in r.get("channel", "") for r in result)


@pytest.mark.asyncio
async def test_unread_needs_auth_when_login_page():
    from sophonic.tools.slack_web import _unread_async

    page = _mock_page(url="https://app.slack.com/signin")
    page.close = AsyncMock()

    with patch("sophonic.browser.persistent_browser") as mock_pb:
        mock_pb.return_value.__aenter__ = AsyncMock(return_value=_ctx_with_page(page))
        mock_pb.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _unread_async("https://app.slack.com")

    assert result == [{"needs_auth": True, "run": "sophonic auth slack"}]


@pytest.mark.asyncio
async def test_search_returns_results():
    from sophonic.tools.slack_web import _search_async

    page = _mock_page(search_texts=["Alice: Have you seen the PR?", "Bob: Yes, LGTM"])

    with patch("sophonic.browser.persistent_browser") as mock_pb:
        mock_pb.return_value.__aenter__ = AsyncMock(return_value=_ctx_with_page(page))
        mock_pb.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _search_async("PR review", "https://app.slack.com")

    assert any("PR" in r.get("text", "") for r in result)
