import asyncio
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import Locator, Page, TimeoutError as PWTimeout


# ---------------------------------------------------------------------------
# Screenshot helpers
# ---------------------------------------------------------------------------

def screenshot_path(label: str, prefix: str = "") -> Path:
    """Return a dated, label-keyed path for screenshots.

    Layout:  screenshots/YYYY-MM-DD/<prefix><safe-label>_HH-MM-SS.png

    Args:
        label:  Human-readable identifier (job title, error tag, etc.)
        prefix: Optional short prefix like "debug_" to distinguish error shots.
    """
    now = datetime.now()
    date_dir = Path("screenshots") / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:60]
    filename = f"{prefix}{safe}_{now.strftime('%H-%M-%S')}.png"
    return date_dir / filename


async def job_label(page: Page) -> str:
    """Extract a short job identifier from the browser page title.

    LinkedIn titles follow: "Job Title at Company | LinkedIn"
    Falls back to the raw title (stripped) if the pattern doesn't match.
    """
    title = (await page.title()) or ""
    return title.split(" | ")[0].strip() or "unknown-job"


# ---------------------------------------------------------------------------
# Retry utilities
# ---------------------------------------------------------------------------

async def click_with_retry(
    page: Page,
    selector: str,
    retries: int = 3,
    delay_ms: int = 800,
) -> None:
    """Click a selector, retrying on timeout.

    Waits for the element to be visible before each attempt so transient
    LinkedIn lazy-load delays don't cause false failures.
    """
    for attempt in range(retries):
        try:
            loc = page.locator(selector)
            await loc.wait_for(state="visible", timeout=5000)
            await loc.click()
            return
        except PWTimeout:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(delay_ms / 1000)


async def fill_with_retry(
    page: Page,
    selector: str,
    value: str,
    retries: int = 3,
) -> None:
    """Fill a field, retrying if not yet attached to DOM.

    Uses state='attached' (not 'visible') because some LinkedIn inputs are
    technically off-screen until scrolled into view.
    """
    for attempt in range(retries):
        try:
            loc = page.locator(selector)
            await loc.wait_for(state="attached", timeout=5000)
            await loc.fill(value)
            return
        except PWTimeout:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Label resolution
# ---------------------------------------------------------------------------

def attr_selector(attr: str, value: str | None) -> str:
    """Build a CSS attribute selector that tolerates LinkedIn URN-style IDs."""
    escaped = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'[{attr}="{escaped}"]'


async def get_label(element: Locator, parent: Locator) -> str | None:
    """Resolve a human-readable label for any input element.

    Tries three strategies in order:
    1. <label for="element-id"> with an aria-hidden span (LinkedIn radio style)
    2. Nearest ancestor <label>
    3. Immediately preceding sibling element (text input style)
    """
    element_id = await element.get_attribute("id")

    # Strategy 1: explicit <label for="id"> containing an aria-hidden span
    if element_id:
        label_el = parent.locator(
            f"label{attr_selector('for', element_id)} span[aria-hidden='true']"
        ).first
        if await label_el.count() > 0:
            return await label_el.text_content()

    # Strategy 2: ancestor <label>
    parent_label = element.locator("xpath=ancestor::label[1]").first
    if await parent_label.count() > 0:
        return await parent_label.text_content()

    # Strategy 3: preceding sibling (covers artdeco-text-input layout where
    # <label> and <input> are siblings inside the same container div)
    sibling = element.locator("xpath=preceding-sibling::*[1]").first
    if await sibling.count() > 0:
        return await sibling.text_content()

    return None


async def get_errors(form: Locator) -> dict[str, str]:
    """Extract the current validation error message for an input, if any.

    Uses aria-describedby on the element to locate the error container,
    then reads the message from [data-test-form-element-error-messages].
    Works for text inputs, selects, checkboxes, and fieldsets (radio groups).

    Uses [id='...'] attribute selectors instead of #id to safely handle
    LinkedIn's URN-format IDs that contain colons and parentheses.
    """
    errors = form.locator("[data-test-form-element-error-messages]")
    error_dict = {}
    for i in range(await errors.count()):
        error = errors.nth(i)
        error_parent = error.locator('..')
        error_element_id = await error_parent.get_attribute("id")
        text = await error.text_content()
        if text:
            error_dict[error_element_id] = text.strip()
    return error_dict



# ---------------------------------------------------------------------------
# Extraction helpers — one per input type
# ---------------------------------------------------------------------------

async def handle_text_field(el: Locator, form: Locator) -> tuple[dict, bool]:
    """Extract a text input or textarea field."""
    element_id = await el.get_attribute("id")
    value = await el.input_value()
    field_type = (await el.get_attribute("type")) or (
        await el.evaluate("el => el.tagName")
    ).lower()
    required = (
        await el.get_attribute("required") is not None
        or await el.get_attribute("aria-required") == "true"
    )
    label = await get_label(el, form)
    is_pending = (required and (not value.strip() or value == "Select an option"))

    return {
        "id": element_id,
        "type": field_type,
        "label": label.strip() if label else None,
        "value": value,
        "checked": False,
        "required": required,
        "options": [],
    }, is_pending


async def handle_combobox_field(el: Locator, form: Locator) -> tuple[dict, bool]:
    """Extract a LinkedIn typeahead combobox field."""
    field, is_pending = await handle_text_field(el, form)
    field["type"] = "combobox"
    return field, is_pending


async def handle_checkbox_field(el: Locator, form: Locator) -> tuple[dict, bool]:
    """Extract a checkbox field — uses is_checked(), not input_value()."""
    element_id = await el.get_attribute("id")
    checked = await el.is_checked()
    required = (
        await el.get_attribute("required") is not None
        or await el.get_attribute("aria-required") == "true"
    )
    label = await get_label(el, form)
    is_pending = (required and not checked)

    return {
        "id": element_id,
        "type": "checkbox",
        "label": label.strip() if label else None,
        "value": "",
        "checked": checked,
        "required": required,
        "options": [],
    }, is_pending


async def handle_select_field(el: Locator, form: Locator) -> tuple[dict, bool]:
    """Extract a <select> field along with all its <option> entries."""
    element_id = await el.get_attribute("id")
    value = await el.input_value()
    required = (
        await el.get_attribute("required") is not None
        or await el.get_attribute("aria-required") == "true"
    )
    label = await get_label(el, form)

    options_locator = el.locator("option")
    option_count = await options_locator.count()
    options = []
    for j in range(option_count):
        opt = options_locator.nth(j)
        options.append({
            "label": (await opt.text_content() or "").strip(),
            "value": await opt.get_attribute("value"),
        })

    is_pending = (required and (not value.strip() or value == "Select an option"))

    return {
        "id": element_id,
        "type": "select",
        "label": label.strip() if label else None,
        "value": value,
        "checked": False,
        "required": required,
        "options": options,
    }, is_pending


def should_skip_prefilled_field(field: dict, is_pending: bool) -> bool:
    """Skip stable, already-filled fields that add noise to the LLM payload."""
    label = (field.get("label") or "").strip().lower()
    return (
        not is_pending
        and field.get("type") == "select"
        and label == "phone country code"
        and bool(str(field.get("value") or "").strip())
    )


async def handle_radio_group(parent: Locator) -> tuple[dict, bool]:
    """Extract a radio group from its fieldset container.

    LinkedIn radio groups use:
      <legend><span data-test-form-builder-radio-button-form-component__title>
        <span aria-hidden='true'>Question text</span>
      </span></legend>

    Radio groups always need LLM resolution, so is_pending is always True.
    """
    label_el = parent.locator("legend span[aria-hidden='true']").first
    label = (await label_el.text_content() or "").strip() if await label_el.count() > 0 else None

    # Error lives on the fieldset via aria-describedby (same pattern as text inputs)
    radio_inputs = parent.locator("input[type='radio']")
    count = await radio_inputs.count()
    options = []
    for j in range(count):
        option = radio_inputs.nth(j)
        radio_id = await option.get_attribute("id")
        label_el = parent.locator(f"label{attr_selector('for', radio_id)}").first
        radio_label = None
        if await label_el.count() > 0:
            raw = await label_el.text_content()
            radio_label = raw.strip() if raw else None
        options.append({
            "radio_id": radio_id,
            "radio_label": radio_label,
            "shouldChecked": "false",
        })

    return {
        "id": None,
        "type": "radio",
        "label": label,
        "value": "",
        "checked": False,
        "required": True,
        "options": options,
    }, True  # radio groups always need LLM resolution


# ---------------------------------------------------------------------------
# Dispatcher — builds the full field list for a form step
# ---------------------------------------------------------------------------

async def handle_inputs(easy_apply_form: Locator) -> dict:
    """Scan every input in the form and return structured field data.

    Returns:
        {
            "pending": bool,          # True if any field still needs a value
            "form_fields": list[dict] # one entry per field
        }
    """
    fields: list[dict] = []
    pending = False
    radio_handled: dict[str, bool] = {}
    is_upload_resume = await easy_apply_form.get_by_text("Upload resume").is_visible()

    # Combobox typeaheads need keyboard selection after filling.
    combobox_locator = easy_apply_form.locator("input[role='combobox']")
    for i in range(await combobox_locator.count()):
        field, is_pending = await handle_combobox_field(
            combobox_locator.nth(i),
            easy_apply_form,
        )
        fields.append(field)
        if is_pending:
            pending = True

    # Text inputs and textareas
    for selector in ("input[type='text']:not([role='combobox'])", "textarea"):
        locator = easy_apply_form.locator(selector)
        for i in range(await locator.count()):
            field, is_pending = await handle_text_field(locator.nth(i), easy_apply_form)
            fields.append(field)
            if is_pending:
                pending = True

    # Select dropdowns
    select_locator = easy_apply_form.locator("select")
    for i in range(await select_locator.count()):
        field, is_pending = await handle_select_field(select_locator.nth(i), easy_apply_form)
        if should_skip_prefilled_field(field, is_pending):
            continue
        fields.append(field)
        if is_pending:
            pending = True

    # Checkboxes
    checkbox_locator = easy_apply_form.locator("input[type='checkbox']")
    for i in range(await checkbox_locator.count()):
        field, is_pending = await handle_checkbox_field(checkbox_locator.nth(i), easy_apply_form)
        fields.append(field)
        if is_pending:
            pending = True

    # Radio groups — skipped on the resume upload step
    if not is_upload_resume:
        radio_locator = easy_apply_form.locator("input[type='radio']")
        for i in range(await radio_locator.count()):
            el = radio_locator.nth(i)
            parent = el.locator("xpath=../..")
            parent_id = await parent.get_attribute("id")
            if not parent_id or radio_handled.get(parent_id):
                continue
            radio_handled[parent_id] = True
            field, is_pending = await handle_radio_group(parent)
            fields.append(field)
            if is_pending:
                pending = True

    errors = await get_errors(easy_apply_form)
    if len(errors) > 0:
        pending = True
    return {"pending": pending, "form_fields": fields, "errors": errors}


# ---------------------------------------------------------------------------
# Fill helpers — one per input type
# ---------------------------------------------------------------------------

async def fill_text_field(page: Page, field: dict) -> None:
    """Fill a text input or textarea.

    Scrolls into view first to avoid 'element not interactable' on fields
    that are below the visible viewport.
    """
    el = page.locator(attr_selector("id", field["id"]))
    await el.scroll_into_view_if_needed()
    await el.fill(field["value"])


async def fill_combobox_field(page: Page, field: dict) -> None:
    """Fill a typeahead combobox and select the first suggestion."""
    el = page.locator(attr_selector("id", field["id"]))
    await el.scroll_into_view_if_needed()
    await el.click()
    await el.fill("")
    await el.fill(field["value"])

    handle = await el.element_handle()
    if handle:
        try:
            await page.wait_for_function(
                "(el) => el.getAttribute('aria-expanded') === 'true' "
                "|| !!el.getAttribute('aria-activedescendant')",
                arg=handle,
                timeout=2000,
            )
        except PWTimeout:
            pass
    else:
        await page.wait_for_timeout(500)

    # Wait after typing
    await page.wait_for_timeout(2000)
    first_option = page.locator("[role='listbox'] [role='option']").first
    try:
        await first_option.wait_for(state="visible", timeout=2000)
        await first_option.click()
    except PWTimeout:
        await page.keyboard.press("ArrowDown")
        await page.keyboard.press("Enter")

    await page.wait_for_timeout(500)


async def fill_select_field(page: Page, field: dict) -> None:
    """Select an option in a <select> by its visible label."""
    el = page.locator(attr_selector("id", field["id"]))
    await el.select_option(label=field["value"])


async def fill_checkbox_field(page: Page, field: dict) -> None:
    """Check a checkbox if the LLM returned a truthy value.

    Prefers clicking the <label> (safer on LinkedIn's custom checkbox
    components) with fallback to the input element directly.
    """
    if field.get("checked"):
        label_el = page.locator(f"label{attr_selector('for', field['id'])}").first
        if await label_el.count() > 0:
            await label_el.click()
        else:
            el = page.locator(attr_selector("id", field["id"]))
            await el.check()


async def fill_radio_field(page: Page, field: dict) -> None:
    """Click the label for whichever radio option the LLM marked shouldChecked."""
    selected_radio_id = next(
        (
            opt["radio_id"]
            for opt in field["options"]
            if (
                isinstance(opt["shouldChecked"], str)
                and opt["shouldChecked"].lower() == "true"
            )
            or (
                isinstance(opt["shouldChecked"], bool)
                and opt["shouldChecked"] is True
            )
        ),
        None,
    )
    if selected_radio_id:
        label_el = page.locator(f"label{attr_selector('for', selected_radio_id)}").first
        await label_el.click()


_FILL_HANDLERS: dict = {
    "combobox": fill_combobox_field,
    "select": fill_select_field,
    "radio": fill_radio_field,
    "checkbox": fill_checkbox_field,
}


async def fill_field(page: Page, field: dict) -> None:
    """Route a filled field dict to the correct fill handler."""
    handler = _FILL_HANDLERS.get(field["type"], fill_text_field)
    await handler(page, field)
