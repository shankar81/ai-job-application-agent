"""Message templates for Telegram prompts.

Kept apart from the client and the orchestrator so tweaking copy (or adding
new templates later — e.g. yes/no inline keyboards) doesn't touch the
HTTP layer.

All output uses Telegram HTML parse_mode. HTML is chosen over Markdown because
LinkedIn field labels and question text often contain underscores, asterisks,
parentheses, and other characters that silently corrupt Telegram's Markdown
parser and produce HTTP 400 errors. With HTML mode we html.escape() every
dynamic value so no user-supplied string can ever break the message.
"""

import html

# Cap any single field/question/job string so a runaway label can't blow
# past Telegram's 4096-char message limit.
_LABEL_MAX = 200
_JOB_MAX = 300


def _shorten(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _e(text: str, limit: int) -> str:
    """Shorten then HTML-escape a dynamic string safe for Telegram HTML mode."""
    return html.escape(_shorten(text, limit))


def build_question_message(
    field: str,
    question: str,
    job_context: str | None = None,
) -> str:
    """Build the initial prompt asking the user to fill in a missing field."""
    lines = [
        "<b>Easy Apply needs your input</b>",
        "",
        f"<b>Field:</b> {_e(field, _LABEL_MAX)}",
        f"<b>Question:</b> {_e(question, _LABEL_MAX)}",
    ]
    if job_context:
        lines.append(f"<b>Job:</b> {_e(job_context, _JOB_MAX)}")
    lines.append("")
    lines.append("<i>Reply to this message with your answer.</i>")
    return "\n".join(lines)


def build_reminder_message(field: str) -> str:
    """Build the follow-up reminder sent after the first attempt times out."""
    return (
        "<b>Still waiting on an answer</b>\n\n"
        f"Field: <code>{_e(field, _LABEL_MAX)}</code>\n\n"
        "<i>Reply to the previous question with your answer. "
        "If no reply arrives soon, this application will be marked as failed.</i>"
    )
