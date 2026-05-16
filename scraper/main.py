import asyncio

from dotenv import load_dotenv
from playwright.async_api import BrowserContext, Page

from scraper.login import login
from scraper.jobs import navigate_to_jobs, scroll_jobs
from scraper.pagination import has_next_page, go_to_next_page
from scraper.session import run_browser_session

load_dotenv()

LINKEDIN_HOME = "https://linkedin.com"

async def run(context: BrowserContext, page: Page) -> None:
    await page.goto(LINKEDIN_HOME)

    if "feed" not in page.url:
        await login(page=page)
        return

    await navigate_to_jobs(context=context, page=page)

    while True:
        await scroll_jobs(page=page)

        if not await has_next_page(page):
            break

        await go_to_next_page(page)


asyncio.run(run_browser_session(run))
