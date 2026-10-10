import logging
import os
import re
from typing import Any

import requests

from monitors.alerts import silence_active
from monitors.config import env


# Telegram puts the bot token in the URL path, and requests includes the URL in
# its exception messages. Anything that may contain a URL goes through redact().
_BOT_TOKEN_PATTERN = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def redact(text: Any, token: Any = None) -> str:
    """Remove Telegram bot tokens from text that is about to be logged or shown."""
    result = _BOT_TOKEN_PATTERN.sub("bot<redacted>", str(text))
    if token:
        result = result.replace(str(token), "<redacted>")
    return result


class TelegramNotifier:
    def __init__(self, config: dict[str, Any], state: Any | None = None) -> None:
        telegram_config = config.get("telegram", {}) or {}
        self.bot_token = (
            os.getenv("TELEGRAM_BOT_TOKEN")
            or env("TELEGRAM_BOT_TOKEN")
            or telegram_config.get("bot_token")
        )
        self.chat_id = (
            os.getenv("TELEGRAM_CHAT_ID")
            or env("TELEGRAM_CHAT_ID")
            or telegram_config.get("chat_id")
        )
        self.state = state
        self.enabled = bool(self.bot_token and self.chat_id)

        if not self.enabled:
            logging.warning(
                "Telegram is disabled. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
                "or telegram.bot_token/chat_id in config.yml."
            )
        else:
            logging.info(
                "Telegram enabled for chat_id=%s with bot token ending in ...%s",
                self.chat_id,
                str(self.bot_token)[-4:],
            )

    def send(self, text: str, force: bool = False) -> None:
        if not self.enabled:
            logging.info("Telegram disabled, would send: %s", text.replace("\n", " | "))
            return

        if not force and self.state and silence_active(self.state):
            logging.info("Alerts silenced, skipped Telegram message: %s", text.replace("\n", " | "))
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            response_text = getattr(getattr(exc, "response", None), "text", "")
            logging.error("Telegram send failed: %s %s", redact(exc, self.bot_token), redact(response_text, self.bot_token))

    def send_alert(self, alert: Any, force: bool = False) -> None:
        labels = {
            "info": "ℹ️ INFO",
            "warning": "⚠️ WARNING",
            "critical": "🚨 CRITICAL",
            "emergency": "🆘 EMERGENCY",
        }
        heading = labels.get(alert.severity, alert.severity.upper())
        self.send(f"{heading}: {alert.title}\n\n{alert.body}", force=force)
