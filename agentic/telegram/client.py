"""Synchronous Telegram Bot API client.

Uses ``urllib`` from the standard library so the package introduces no new
runtime dependencies. The client knows how to:

  * send a message to the configured chat
  * long-poll ``getUpdates`` for a reply addressed to a specific message_id

Why long polling (no webhooks): this bot runs on the user's laptop without a
public URL, and Telegram's long-poll endpoint is exactly designed for that.
We use a 25-second poll window to keep request volume low.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional


def _build_ssl_context() -> ssl.SSLContext:
    """Return an SSL context that trusts the OS keychain when possible.

    On macOS / Windows, ``truststore`` exposes the system trust store to
    Python. This matters when a corporate VPN, antivirus, or Zscaler-style
    proxy injects a root CA into the system store — ``urllib``'s stdlib
    default doesn't read those, so HTTPS calls fail with
    ``SSL: CERTIFICATE_VERIFY_FAILED`` even though Safari/Chrome work fine.

    Falls back to the stdlib default if ``truststore`` isn't installed.
    """
    try:
        import truststore  # type: ignore[import-not-found]

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


_SSL_CONTEXT = _build_ssl_context()

# Telegram REST endpoint template
_API_URL = "https://api.telegram.org/bot{token}/{method}"

# Hold the HTTP connection open up to this many seconds waiting for updates.
# Telegram caps this at 50; 25 is a comfortable middle ground.
LONG_POLL_SECONDS = 25

# Default per-call HTTP timeout, slightly above the long-poll window so we
# don't kill the socket while Telegram is still legitimately holding it.
_DEFAULT_HTTP_TIMEOUT = LONG_POLL_SECONDS + 10


class TelegramError(Exception):
    """Raised for HTTP errors or non-OK Telegram API responses."""


class TelegramClient:
    """Thin wrapper around the subset of Bot API methods we use."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        # ``getUpdates`` uses an ever-increasing offset. ``None`` means we
        # haven't primed it yet — we will skip whatever backlog is sitting
        # on Telegram's side so old messages can't satisfy a wait_for_reply.
        self._last_update_id: int | None = None

    # ------------------------------------------------------------------ HTTP

    def _call(
        self,
        method: str,
        params: dict,
        timeout: float = _DEFAULT_HTTP_TIMEOUT,
    ) -> dict | list:
        """POST to the given Bot API method and return the parsed ``result`` field."""
        url = _API_URL.format(token=self._token, method=method)
        data = urllib.parse.urlencode(params).encode("utf-8")
        try:
            with urllib.request.urlopen(
                url, data=data, timeout=timeout, context=_SSL_CONTEXT
            ) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise TelegramError(f"{method} request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise TelegramError(f"{method} returned non-JSON body") from exc

        if not payload.get("ok"):
            raise TelegramError(f"{method} returned error: {payload}")
        return payload["result"]

    # ----------------------------------------------------------- public API

    def send_message(self, text: str, parse_mode: str = "Markdown") -> int:
        """Send ``text`` to the configured chat. Returns the bot's ``message_id``."""
        result = self._call(
            "sendMessage",
            {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": "true",
            },
            timeout=30,
        )
        return result["message_id"]

    def wait_for_reply(
        self,
        message_id: int,
        timeout_seconds: int,
    ) -> Optional[str]:
        """Block until a reply to ``message_id`` arrives, or ``timeout_seconds`` elapse.

        Returns the reply's text on success, or ``None`` on timeout.

        Matching is strict: we only accept updates whose
        ``message.reply_to_message.message_id`` equals ``message_id``. This means
        the user must use Telegram's "reply" gesture (swipe / long-press) rather
        than sending a free-form message. This avoids confusion if multiple
        questions are in flight or if the user types something unrelated.
        """
        if self._last_update_id is None:
            self._prime_offset()

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = int(deadline - time.monotonic())
            poll_window = min(LONG_POLL_SECONDS, max(1, remaining))
            try:
                updates = self._call(
                    "getUpdates",
                    {
                        "offset": (self._last_update_id or 0) + 1,
                        "timeout": poll_window,
                        # Only ask for message updates — ignore edits/reactions
                        "allowed_updates": json.dumps(["message"]),
                    },
                    timeout=poll_window + 10,
                )
            except TelegramError as exc:
                # Transient network blip — log, back off briefly, retry until
                # the deadline. We do NOT bubble out, otherwise a single dropped
                # request would cancel the whole wait.
                print(f"[telegram] Poll error: {exc}. Retrying.")
                time.sleep(2)
                continue

            for update in updates:
                update_id = update.get("update_id")
                if update_id is not None:
                    self._last_update_id = max(self._last_update_id or 0, update_id)

                message = update.get("message") or {}
                reply_to = message.get("reply_to_message") or {}
                if reply_to.get("message_id") != message_id:
                    continue

                text = (message.get("text") or "").strip()
                if text:
                    return text

        return None

    # ------------------------------------------------------------- internal

    def _prime_offset(self) -> None:
        """Discover the current ``update_id`` baseline so old messages are ignored."""
        try:
            updates = self._call("getUpdates", {"timeout": 0}, timeout=10)
        except TelegramError:
            # If we can't reach Telegram at startup, start from 0 — the next
            # poll will retry and update us once the network recovers.
            self._last_update_id = 0
            return

        self._last_update_id = (
            max((u["update_id"] for u in updates), default=0) if updates else 0
        )
