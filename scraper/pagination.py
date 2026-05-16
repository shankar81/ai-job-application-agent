from playwright.async_api import Page

NEXT_BUTTON_SELECTOR = "button[data-testid='pagination-controls-next-button-visible']"


async def has_next_page(page: Page) -> bool:
    """Return True if a next-page button is present and clickable."""
    next_button = page.locator(NEXT_BUTTON_SELECTOR)
    return await next_button.count() > 0


async def go_to_next_page(page: Page) -> None:
    """
    Dismiss any open overlay, scroll the next-page button into view,
    and click it. Waits for the new page to settle.
    """
    next_button = page.locator(NEXT_BUTTON_SELECTOR)
    await page.keyboard.press("Escape")
    await page.mouse.click(10, 10)
    await next_button.scroll_into_view_if_needed()
    await next_button.first.click()
    await page.wait_for_timeout(3000)
