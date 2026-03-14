#!/usr/bin/env python3
"""
Standalone bot listener runner.
Keeps the Telegram polling loop alive in the main (non-daemon) thread.
"""

import logging
import os
import sys

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
)
logger = logging.getLogger("bot_runner")


def main() -> None:
    from src.bot.telegram_listener import _poll_loop

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
        raise SystemExit(1)

    logger.info("Bot runner started. Listening for messages...")

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "Bot listener started. Send 'help' for commands."},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Bot runner could not send startup message: %s", exc)

    _poll_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
