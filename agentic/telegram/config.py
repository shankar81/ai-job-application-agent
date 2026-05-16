"""Telegram configuration loader.

Reads ``TELEGRAM_BOT_TOKEN``, ``TELEGRAM_CHAT_ID``, ``TELEGRAM_REPLY_TIMEOUT``
and ``TELEGRAM_MAX_ATTEMPTS`` from the process environment.

``.env`` is loaded by ``agentic/nodes.py`` (and ``agentic/agent.py``) so by the
time anything inside this package runs, ``os.environ`` already has the values.

The values are intentionally read fresh on every ``load_config()`` call so
tests can override them via ``monkeypatch.setenv`` without having to reload
the module.
"""

import os
from dataclasses import dataclass

# Default: wait 5 minutes per attempt. Override with TELEGRAM_REPLY_TIMEOUT.
DEFAULT_REPLY_TIMEOUT_SECONDS = 300

# Default: 2 attempts = one initial send + one reminder.
DEFAULT_MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class TelegramConfig:
    """Parsed, validated Telegram settings."""

    bot_token: str
    chat_id: str
    reply_timeout: int
    max_attempts: int


def _int_env(name: str, default: int) -> int:
    """Read an integer env var, tolerating inline ``# comment`` suffixes."""
    raw = os.getenv(name)
    if not raw:
        return default
    # python-dotenv usually strips inline comments, but only when there's
    # whitespace before the ``#``. Be defensive in case the user writes
    # ``300# comment`` with no space.
    raw = raw.split("#", 1)[0].strip()
    try:
        return int(raw)
    except ValueError:
        return default


def load_config() -> TelegramConfig | None:
    """Return a fully populated config, or ``None`` if required fields are missing."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return None

    return TelegramConfig(
        bot_token=token,
        chat_id=chat_id,
        reply_timeout=_int_env("TELEGRAM_REPLY_TIMEOUT", DEFAULT_REPLY_TIMEOUT_SECONDS),
        max_attempts=_int_env("TELEGRAM_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS),
    )


def is_configured() -> bool:
    """Convenience predicate: ``True`` if Telegram is usable right now."""
    return load_config() is not None
