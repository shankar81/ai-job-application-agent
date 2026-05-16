from playwright.async_api import Locator, Page, TimeoutError as PWTimeout

from agentic.agent import app, checkpoint_config
from scraper.helpers import fill_field, handle_inputs, job_label, screenshot_path

# Selector for the LinkedIn Easy Apply modal
EASY_APPLY_MODAL_SELECTOR = 'div[data-test-modal-id="easy-apply-modal"]'
EASY_APPLY_SELECTORS = [
    "a[aria-label*='Easy Apply']",
    "button[aria-label*='Easy Apply']",
    "a:has-text('Easy Apply')",
    "button:has-text('Easy Apply')",
]

# Post-apply confirmation modal — stable via aria-labelledby set by LinkedIn
POST_SUBMIT_SELECTOR = '[data-test-modal][aria-labelledby="post-apply-modal"]'

# Dismiss X button inside the post-apply modal
POST_SUBMIT_DISMISS_SELECTOR = f"{POST_SUBMIT_SELECTOR} button[data-test-modal-close-btn]"

POST_SUBMIT_CONFIRMATION_SELECTORS = [
    POST_SUBMIT_SELECTOR,
    "[data-test-modal]:has-text('Application sent')",
    "div[role='dialog']:has-text('Application sent')",
    "text=Your application was sent",
]

# Bail out if the modal somehow loops this many times
MAX_MODAL_DEPTH = 10


async def wait_for_submit_confirmation(page: Page) -> bool:
    """Return True when LinkedIn shows the post-submit success UI."""
    for selector in POST_SUBMIT_CONFIRMATION_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=2500)
            return True
        except PWTimeout:
            continue

    return False


async def dismiss_post_submit_modal(page: Page) -> None:
    """Dismiss LinkedIn's post-submit modal when possible."""
    done = page.get_by_role("button", name="Done")
    try:
        if await done.count() > 0 and await done.is_visible(timeout=1000):
            await done.click()
            return
    except PWTimeout:
        pass

    dismiss = page.locator(POST_SUBMIT_DISMISS_SELECTOR)
    if await dismiss.count() > 0:
        await dismiss.click()


async def find_easy_apply_button(page: Page) -> Locator | None:
    """Find the visible Easy Apply control, whether LinkedIn renders it as a link or button."""
    for selector in EASY_APPLY_SELECTORS:
        locator = page.locator(selector).first
        try:
            if await locator.count() > 0 and await locator.is_visible(timeout=1000):
                return locator
        except PWTimeout:
            continue

    return None


async def has_easy_apply_button(page: Page) -> bool:
    return await find_easy_apply_button(page) is not None


async def easy_apply_flow(page: Page) -> bool:
    """Entry point: click Easy Apply and hand off to the step handler."""
    try:
        easy_apply = await find_easy_apply_button(page)
        if easy_apply is None:
            print("[easy_apply] Easy Apply button not visible.")
            return False
        await easy_apply.click()

        easy_apply_modal = page.locator(EASY_APPLY_MODAL_SELECTOR)
        await easy_apply_modal.wait_for()
        easy_apply_form = easy_apply_modal.locator("form").first
        await easy_apply_form.wait_for()

        return await handle_easy_apply_form(easy_apply_modal, easy_apply_form)

    except Exception as exc:
        shot_path = screenshot_path(f"error-{await job_label(page)}", prefix="debug_")
        await page.screenshot(path=str(shot_path), full_page=True)
        print(f"[easy_apply] Error: {exc}. Screenshot saved: {shot_path}")
        raise


async def handle_easy_apply_form(
    easy_apply_modal: Locator,
    easy_apply_form: Locator,
    modal_count: int = 0,
) -> bool:
    """Handle one modal step, recursing through next/review until submit.

    Args:
        easy_apply_modal: Locator for the modal container (stable across steps).
        easy_apply_form:  Locator for the current form step.
        modal_count:      Recursion depth — guards against infinite loops.
    """
    if modal_count >= MAX_MODAL_DEPTH:
        print(f"[easy_apply] Reached max depth ({MAX_MODAL_DEPTH}), bailing out.")
        return False

    page = easy_apply_form.page

    # Extract all form fields and fill any that are still pending
    form_response = await handle_inputs(easy_apply_form)
    if form_response["pending"]:
        result = app.invoke(
            {"job_url": page.url, "form_fields": form_response["form_fields"], "errors": form_response["errors"]},
            config=checkpoint_config,
        )
        print(f"[easy_apply] Filling {len(result['form_fields'])} pending fields.")
        for field in result["form_fields"]:
            await fill_field(page, field)

    # Re-query form after fills — LinkedIn may re-render on conditional fields
    easy_apply_form = easy_apply_modal.locator("form").first

    print(f"[easy_apply] Modal step: {modal_count}")

    # ── Next step ────────────────────────────────────────────────────────────
    next_button = easy_apply_form.locator("button[aria-label*='next step']")
    if await next_button.count() > 0 and await next_button.is_enabled():
        await next_button.click()
        print("[easy_apply] → NEXT")
        return await handle_easy_apply_form(easy_apply_modal, easy_apply_form, modal_count + 1)

    # ── Review step ──────────────────────────────────────────────────────────
    review_button = easy_apply_form.locator("button[aria-label*='Review']")
    if await review_button.count() > 0 and await review_button.is_enabled():
        await review_button.click()
        print("[easy_apply] → REVIEW")
        return await handle_easy_apply_form(easy_apply_modal, easy_apply_form, modal_count + 1)

    # ── Submit ───────────────────────────────────────────────────────────────
    await easy_apply_modal.evaluate(
        "el => el.scrollTop = el.scrollHeight"
    )
    submit_button = easy_apply_modal.locator("button[aria-label*='Submit']")
    if await submit_button.count() > 0 and await submit_button.is_enabled():
        await submit_button.click()
        print("[easy_apply] → SUBMITTED")
        await page.wait_for_timeout(5000)
        confirmed = await wait_for_submit_confirmation(page)
        if confirmed:
            print("[easy_apply] Application submitted successfully.")
        else:
            print("[easy_apply] Submit confirmation not detected — application may still have gone through.")

        # Screenshot while post-apply modal is still open (before dismissing)
        shot_path = screenshot_path(await job_label(page))
        await page.screenshot(path=str(shot_path), full_page=True)
        print(f"[easy_apply] Submit screenshot saved: {shot_path}")

        # Dismiss via the X icon in the modal header
        if confirmed:
            await dismiss_post_submit_modal(page)
        return confirmed

    # No recognised button — pause for manual inspection
    print("[easy_apply] No actionable button found at step", modal_count)
    await page.pause()
    return False
