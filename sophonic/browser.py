"""Playwright persistent browser context — chromium / chrome / island."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sophonic.config import config_dir, load_config


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
        "Set [browser.island] path = '...' in ~/.sophonic/config.toml"
    )


@asynccontextmanager
async def persistent_browser(
    integration: str,
    headless: bool | None = None,
    cookies: list[dict] | None = None,
) -> AsyncGenerator:
    """
    Yield a Playwright BrowserContext backed by a persistent user-data-dir.

    Opened headed on first run (no session saved) so the user can log in.
    Subsequent calls run headless unless headless=False is forced.

    integration: "slack" | "zoom"
    cookies: optional list of Playwright cookie dicts seeded into the context
        (used to reuse a session captured elsewhere, e.g. pasted Zoom cookies).
    """
    from playwright.async_api import async_playwright

    engine_cfg = getattr(load_config().browser, integration, None)
    engine = engine_cfg.engine if engine_cfg else "chromium"
    profile = _profile_dir(integration, engine)

    has_session = any(profile.iterdir()) if profile.exists() else False
    # With seeded cookies we already have a session, so default to headless.
    use_headless = headless if headless is not None else (has_session or bool(cookies))

    launch_kwargs: dict = {
        "user_data_dir": str(profile),
        "headless": use_headless,
        "args": ["--no-first-run", "--no-default-browser-check"],
    }

    async with async_playwright() as pw:
        try:
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
        except Exception as exc:
            if engine == "island":
                raise RuntimeError(
                    "Island could not be automated. Enterprise policy blocks the DevTools "
                    "remote-debugging interface Playwright needs ('DevTools remote debugging "
                    "is disallowed by the system admin'), so Sophonic cannot drive Island. "
                    "Switch the engine (`sophonic config set browser."
                    f"{integration}.engine chromium`) — note this only works if your Okta/SSO "
                    "login also works outside Island — or use an API-based integration instead."
                ) from exc
            raise

        if cookies:
            await ctx.add_cookies(cookies)

        try:
            yield ctx
        finally:
            await ctx.close()


async def open_auth_browser(integration: str, url: str) -> None:
    """Open a headed browser at url so the user can log in once."""
    async with persistent_browser(integration, headless=False) as ctx:
        # A persistent context already has an initial page. Reuse it and bring it to
        # front so we drive the window the user actually sees — some managed browsers
        # open new_page() in the background (or a separate window).
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.bring_to_front()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            print(f"[sophonic] Opened {page.url}")
        except Exception as exc:
            print(
                f"[sophonic] Could not auto-load {url}: {exc}\n"
                f"[sophonic] Navigate to {url} manually in the open window."
            )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: input(
                f"\n[sophonic] Log in to {integration} in the browser, "
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
