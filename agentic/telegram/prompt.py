"""High-level ``ask_user`` orchestrator.

This is the only symbol the agent layer should import from this package.
It composes ``config``, ``client``, and ``formatter`` to:

  1. Validate Telegram is configured.
  2. Send the question.
  3. Long-poll for a reply for ``reply_timeout`` seconds.
  4. If no reply arrived, send a reminder and poll once more.
  5. Raise ``TelegramReplyTimeout`` if all attempts elapsed.

Exceptions are deliberately specific so callers (e.g. the agent tool) can
decide whether to abort the application, fall back to ``input()``, or
surface the failure to the user differently.
"""

from agentic.telegram.client import TelegramClient, TelegramError
from agentic.telegram.config import load_config
from agentic.telegram.formatter import (
    build_question_message,
    build_reminder_message,
)


class TelegramNotConfigured(Exception):
    """Raised when ``TELEGRAM_BOT_TOKEN`` or ``TELEGRAM_CHAT_ID`` is missing."""


class TelegramReplyTimeout(Exception):
    """Raised when no reply was received within the configured attempts."""


def ask_user(
    field: str,
    question: str,
    job_context: str | None = None,
) -> str:
    """Ask the user a question via Telegram and return their reply.

    Args:
        field: Stable form-field identifier (used in the message body).
        question: Human-readable question text (e.g. the LinkedIn label).
        job_context: Optional job title or URL so the user knows which
            application they're answering for.

    Returns:
        The reply text (stripped).

    Raises:
        TelegramNotConfigured: env vars missing.
        TelegramReplyTimeout: send failed or no reply across all attempts.
    """
    config = load_config()
    if config is None:
        raise TelegramNotConfigured(
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env to use Telegram prompts."
        )

    client = TelegramClient(config.bot_token, config.chat_id)

    try:
        message_id = client.send_message(
            build_question_message(field, question, job_context)
        )
    except TelegramError as exc:
        # Treat a failed initial send the same as a timeout — the caller
        # already has a code path for "no answer".
        raise TelegramReplyTimeout(f"Failed to send question: {exc}") from exc

    print(
        f"[telegram] Question sent (message_id={message_id}); "
        f"waiting up to {config.reply_timeout}s for a reply."
    )

    for attempt in range(1, config.max_attempts + 1):
        reply = client.wait_for_reply(message_id, config.reply_timeout)
        if reply:
            print(f"[telegram] Got reply on attempt {attempt}.")
            return reply

        is_last_attempt = attempt == config.max_attempts
        if is_last_attempt:
            break

        print(
            f"[telegram] No reply after attempt {attempt}/"
            f"{config.max_attempts}. Sending reminder."
        )
        try:
            client.send_message(build_reminder_message(field))
        except TelegramError as exc:
            # Reminder is best-effort. If it fails, we still wait one more
            # cycle — the user might still reply to the original question.
            print(f"[telegram] Reminder send failed: {exc}")

    raise TelegramReplyTimeout(
        f"No Telegram reply after {config.max_attempts} attempts "
        f"(~{config.max_attempts * config.reply_timeout}s total)."
    )
