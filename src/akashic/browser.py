"""Playwright persistent browser context — chromium / chrome / island."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from akashic.config import config_dir, load_config


def _profile_dir(integration: str, engine: str) -> Path:
    d = config_dir() / "playwright-profile" / f"{engine}-{integration}"
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def _island_executable() -> str:
    cfg = load_config().browser.island
    if cfg.path:
        return cfg.path
    default = "/Applications/Island.app/Contents/MacOS/Island"
    if Path(default).exists():
        return default
    raise FileNotFoundError(
        "Island browser not found at /Applications/Island.app/. "
        "Set [browser.island] path = '...' in ~/.akashic/config.toml"
    )


@asynccontextmanager
async def persistent_browser(
    integration: str,
    headless: bool | None = None,
) -> AsyncGenerator:
    """
    Yield a Playwright BrowserContext backed by a persistent user-data-dir.

    Opened headed on first run (no session saved) so the user can log in.
    Subsequent calls run headless unless headless=False is forced.

    integration: "slack" | "zoom"
    """
    from playwright.async_api import async_playwright

    engine_cfg = getattr(load_config().browser, integration, None)
    engine = engine_cfg.engine if engine_cfg else "chromium"
    profile = _profile_dir(integration, engine)

    has_session = any(profile.iterdir()) if profile.exists() else False
    use_headless = headless if headless is not None else has_session

    launch_kwargs: dict = {
        "user_data_dir": str(profile),
        "headless": use_headless,
        "args": ["--no-first-run", "--no-default-browser-check"],
    }

    async with async_playwright() as pw:
        if engine == "chromium":
            ctx = await pw.chromium.launch_persistent_context(**launch_kwargs)
        elif engine == "chrome":
            ctx = await pw.chromium.launch_persistent_context(
                channel="chrome", **launch_kwargs
            )
        elif engine == "island":
            ctx = await pw.chromium.launch_persistent_context(
                executable_path=_island_executable(), **launch_kwargs
            )
        else:
            raise ValueError(f"Unknown engine: {engine!r}")

        try:
            yield ctx
        finally:
            await ctx.close()


async def open_auth_browser(integration: str, url: str) -> None:
    """Open a headed browser at url so the user can log in once."""
    async with persistent_browser(integration, headless=False) as ctx:
        page = await ctx.new_page()
        await page.goto(url)
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: input(
                f"\n[akashic] Log in to {integration} in the browser, "
                "then press Enter here to save the session...\n"
            ),
        )


def run_async(coro):
    """Run a coroutine from sync code, working whether or not a loop is running."""
    try:
        asyncio.get_running_loop()
        # Already inside an event loop (e.g. FastMCP): run in a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)
