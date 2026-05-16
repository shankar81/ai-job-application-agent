
import os
from playwright.async_api import Page


async def login(page: Page) -> None:
    EMAIL = os.getenv("EMAIL") or ""
    PASSWORD = os.getenv("PASSWORD") or ""
    await page.get_by_role("link", name="Sign in").first.click()
    # fill in the email and password
    username = page.get_by_label("Email or phone", exact=True).last
    password = page.get_by_label("Password", exact=True).last
    submit = page.get_by_role(
        "button",
        name="Sign in",
        exact=True
    )
    await username.click()
    await username.wait_for()
    await submit.wait_for()
    await username.fill(EMAIL)
    await password.fill(PASSWORD)
    await submit.click()
    # await page.wait_for_url("https://www.linkedin.com/feed/*")