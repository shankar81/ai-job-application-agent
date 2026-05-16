"""Message templates for Telegram prompts.

Kept apart from the client and the orchestrator so tweaking copy (or adding
new templates later — e.g. yes/no inline keyboards) doesn't touch the
HTTP layer.

All output is Telegram-flavoured Markdown.
"""

# Cap any single field/question/job string so a runaway label can't blow
# past Telegram's 4096-char message limit.
_LABEL_MAX = 200
_JOB_MAX = 300


def _shorten(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_question_message(
    field: str,
    question: str,
    job_context: str | None = None,
) -> str:
    """Build the initial prompt asking the user to fill in a missing field."""
    lines = [
        "*Easy Apply needs your input*",
        "",
        f"*Field:* {_shorten(field, _LABEL_MAX)}",
        f"*Question:* {_shorten(question, _LABEL_MAX)}",
    ]
    if job_context:
        lines.append(f"*Job:* {_shorten(job_context, _JOB_MAX)}")
    lines.append("")
    lines.append("_Reply to this message with your answer._")
    return "\n".join(lines)


def build_reminder_message(field: str) -> str:
    """Build the follow-up reminder sent after the first attempt times out."""
    return (
        "*Still waiting on an answer*\n\n"
        f"Field: `{_shorten(field, _LABEL_MAX)}`\n\n"
        "_Reply to the previous question with your answer. "
        "If no reply arrives soon, this application will be marked as failed._"
    )
