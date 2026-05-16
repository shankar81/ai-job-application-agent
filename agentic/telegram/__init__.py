"""Telegram notification layer for the agent.

Public API:
    ask_user(field, question, job_context=None) -> str
    TelegramNotConfigured
    TelegramReplyTimeout

Only ``prompt.ask_user`` and the two exception types should be imported
by callers outside this package. The HTTP client, formatter, and config
loader are implementation details.
"""

from agentic.telegram.prompt import (
    TelegramNotConfigured,
    TelegramReplyTimeout,
    ask_user,
)

__all__ = ["ask_user", "TelegramNotConfigured", "TelegramReplyTimeout"]
