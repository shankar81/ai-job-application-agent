from datetime import datetime
from typing import TypedDict

from playwright.async_api import BrowserContext, Locator, Page

from agentic.agent import app, checkpoint_config
from agentic.tools import update_job_application_status
from scraper.easy_apply import easy_apply_flow, has_easy_apply_button

AUTH_STATE_PATH = "auth.json"
JOBS_SEARCH_SELECTOR = "a[href*='software+engineer+Easy+Apply']"
JOBS_CONTAINER_SELECTOR = "div[data-testid='lazy-column']"
# componentkey attribute is stable: present on every job card div[role='button']
# and avoids accidentally matching other role=button divs inside the container
JOB_CARD_SELECTOR = "div[role='button'][componentkey]"
MATCH_SCORE_THRESHOLD = 5
JOBS_FILE_PATH = "./storage/jobs.xlsx"
EXTERNAL_APPLY_STATUS = "external_apply_required"


class Job(TypedDict):
    link: str
    extracted_on: datetime
    JD: str


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

async def navigate_to_jobs(context: BrowserContext, page: Page) -> None:
    """Go to LinkedIn Jobs, persist auth state, and open the target search."""
    await page.goto("https://www.linkedin.com/jobs/")
    await context.storage_state(path=AUTH_STATE_PATH)

    job_link = page.locator(JOBS_SEARCH_SELECTOR)
    await job_link.first.wait_for()
    await job_link.first.click()


# ---------------------------------------------------------------------------
# Job detail extraction
# ---------------------------------------------------------------------------

async def extract_job_details(page: Page) -> str:
    """Scrape the full text of the job detail panel (right side).

    Clicks the 'Show more' expand button (data-testid='expandable-text-button')
    if present so the full job description is loaded before reading.
    """
    details_panel = page.locator(JOBS_CONTAINER_SELECTOR).last
    await details_panel.wait_for()

    # Grab the expanded text box specifically (avoids duplicate text)
    expandable = details_panel.locator(
        "[data-testid='expandable-text-box']"
    ).first
    expanded_text = ""
    if await expandable.count() > 0:
        expanded_text = await expandable.text_content() or ""

    return (await details_panel.text_content() or "") + expanded_text


# ---------------------------------------------------------------------------
# Per-card processing
# ---------------------------------------------------------------------------

async def process_job_card(page: Page, card: Locator) -> Job:
    """
    Click a job card, build a Job record from its text + detail panel,
    then trigger the Easy Apply flow.
    """
    await card.click()
    await page.wait_for_timeout(2000)

    job: Job = {
        "link": page.url,
        "extracted_on": datetime.now(),
        "JD": (await card.text_content() or "") + (await extract_job_details(page=page)),
    }

    if await is_already_applied(page):
        print("[jobs] LinkedIn shows already applied, skipping match and Easy Apply.")
        update_job_application_status(JOBS_FILE_PATH, page.url, "applied")
        return job

    if not await has_easy_apply_button(page):
        status = EXTERNAL_APPLY_STATUS if await has_external_apply_button(page) else "failed"
        error = "" if status == EXTERNAL_APPLY_STATUS else "No Easy Apply button available"
        print(f"[jobs] Easy Apply unavailable, marking {status}.")
        update_job_application_status(
            JOBS_FILE_PATH,
            page.url,
            status,
            error,
        )
        return job

    result = app.invoke({"job_url": page.url, "raw_job_desc": job, "form_fields": None}, config=checkpoint_config)
    match_score = float(result.get("match_score", 0) or 0)
    application_status = result.get("application_status", "not_applied")
    print(f"[jobs] Match score: {match_score}")

    if application_status == "applied":
        if await has_easy_apply_button(page):
            print("[jobs] XLS says applied, but Easy Apply is visible; continuing.")
        else:
            print("[jobs] XLS status is already applied, skipping Easy Apply.")
            return job

    if match_score <= MATCH_SCORE_THRESHOLD:
        print(f"[jobs] Match score <= {MATCH_SCORE_THRESHOLD}, skipping Easy Apply.")
        update_job_application_status(
            JOBS_FILE_PATH,
            page.url,
            "skipped_low_score",
        )
        return job

    try:
        applied = await easy_apply_flow(page)
        if applied:
            update_job_application_status(JOBS_FILE_PATH, page.url, "applied")
        else:
            update_job_application_status(
                JOBS_FILE_PATH,
                page.url,
                "failed",
                "Easy Apply unavailable or submit confirmation missing",
            )
    except Exception as exc:
        update_job_application_status(
            JOBS_FILE_PATH,
            page.url,
            "failed",
            str(exc)[:500],
        )
        raise

    return job


async def is_already_applied(page: Page) -> bool:
    """Detect LinkedIn's selected-job application status before scoring."""
    details_panel = page.locator(JOBS_CONTAINER_SELECTOR).last
    status_selectors = [
        "text=/^Application submitted$/i",
        "text=/^Applied$/i",
    ]

    for selector in status_selectors:
        if await details_panel.locator(selector).count() > 0:
            return True

    return False


async def has_external_apply_button(page: Page) -> bool:
    """Detect LinkedIn jobs that require applying outside LinkedIn."""
    details_panel = page.locator(JOBS_CONTAINER_SELECTOR).last
    apply_button = details_panel.get_by_role("link", name="Apply")
    if await apply_button.count() > 0:
        return True

    return await details_panel.get_by_text("Responses managed off LinkedIn").count() > 0


# ---------------------------------------------------------------------------
# Page-level scroll
# ---------------------------------------------------------------------------

async def scroll_jobs(page: Page) -> list[Job]:
    """
    Iterate every job card visible on the current results page,
    process each one, and return the collected Job records.
    """
    await page.wait_for_timeout(5000)

    jobs_container = page.locator(JOBS_CONTAINER_SELECTOR).first
    await jobs_container.wait_for()

    job_cards = jobs_container.locator(JOB_CARD_SELECTOR)
    count = await job_cards.count()
    print(f"Found {count} job cards on this page")

    job_details: list[Job] = []
    for i in range(count):
        card = job_cards.nth(i)
        job = await process_job_card(page, card)
        job_details.append(job)

    return job_details
