from typing import Callable, Awaitable
from playwright.async_api import async_playwright, BrowserContext, Page

USERDATA_DIR: str = "./userdata"
HEADLESS: bool = False
SLOW_MO: float = 1000


async def run_browser_session(
    task: Callable[[BrowserContext, Page], Awaitable[None]]
) -> None:
    """
    Launch a persistent Chromium browser context and hand it to `task`.
    Handles setup and graceful teardown automatically.

    Usage:
        async def run(context, page):
            ...
        asyncio.run(run_browser_session(run))
    """
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            USERDATA_DIR,
            headless=HEADLESS,
            slow_mo=SLOW_MO,
        )
        page = context.pages[0]
        try:
            await task(context, page)
        finally:
            await page.wait_for_timeout(5000)
            await context.close()
