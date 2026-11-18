"""Playwright persistent browser context — chromium / chrome / island.

Only used by the Zoom cookie fallback (`sophonic/zoom.py`), which runs when no Zoom MCP
is available. The default Zoom path is the MCP and needs none of this.
"""

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

    integration: "zoom" (the only browser-driven integration)
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
