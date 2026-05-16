"""Smoke test for the Telegram package.

Run on your Mac (not the sandbox) — Cowork's sandbox blocks outbound
traffic to api.telegram.org.

Usage:
    python scripts/smoke_test_telegram.py            # send-only test
    python scripts/smoke_test_telegram.py --reply    # send + wait for your reply
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from agentic.telegram.client import TelegramClient, TelegramError
from agentic.telegram.config import load_config


def main() -> int:
    config = load_config()
    if config is None:
        print("FAIL: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in .env")
        return 1

    print(
        f"Config OK — chat_id={config.chat_id}, "
        f"timeout={config.reply_timeout}s, max_attempts={config.max_attempts}"
    )

    client = TelegramClient(config.bot_token, config.chat_id)

    # --- Send leg ---------------------------------------------------------
    try:
        message_id = client.send_message(
            "*Smoke test from automation bot*\n\n"
            "If you can read this, the send leg works."
        )
    except TelegramError as exc:
        print(f"FAIL: send_message error: {exc}")
        return 1
    print(f"OK: sent message_id={message_id}")

    # --- Optional reply leg ----------------------------------------------
    if "--reply" not in sys.argv:
        print("Skipping reply test. Pass --reply to also test the wait path.")
        return 0

    print("Now reply to that message on Telegram (long-press → Reply).")
    print("Waiting up to 60 seconds…")

    reply = client.wait_for_reply(message_id, timeout_seconds=60)
    if reply is None:
        print("FAIL: no reply received within 60s")
        return 1

    print(f"OK: got reply → {reply!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
