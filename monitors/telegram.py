import html
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
_TAG_PATTERN = re.compile(r"</?(b|i|u|s|code|pre|blockquote)(\s[^>]*)?>")

# Telegram limits callback data to 64 bytes.
MAX_CALLBACK_BYTES = 64

# One inline button: (label, callback data). Rows of buttons form a keyboard.
Button = tuple[str, str]
Buttons = list[list[Button]]


def redact(text: Any, token: Any = None) -> str:
    """Remove Telegram bot tokens from text that is about to be logged or shown."""
    result = _BOT_TOKEN_PATTERN.sub("bot<redacted>", str(text))
    if token:
        result = result.replace(str(token), "<redacted>")
    return result


def esc(value: Any) -> str:
    """Escape a value for Telegram's HTML parse mode."""
    return html.escape(str(value), quote=False)


def plain(text: str) -> str:
    """Strip the HTML tags Sheltie uses, for the plain-text fallback."""
    return html.unescape(_TAG_PATTERN.sub("", text))


def keyboard(buttons: Buttons | None) -> dict[str, Any] | None:
    rows = []
    for row in buttons or []:
        cells = [
            {"text": label, "callback_data": data}
            for label, data in row
            if len(data.encode("utf-8")) <= MAX_CALLBACK_BYTES
        ]
        if cells:
            rows.append(cells)
    return {"inline_keyboard": rows} if rows else None


SEVERITY_LABELS = {
    "info": ("ℹ️", "Info"),
    "warning": ("⚠️", "Warning"),
    "critical": ("🚨", "Critical"),
    "emergency": ("🆘", "Emergency"),
}


def format_body(body: str) -> str:
    """Bold the "Key:" part of "Key: value" lines so alert details scan quickly."""
    lines = []
    for line in str(body).splitlines():
        key, sep, value = line.partition(": ")
        if sep and 0 < len(key) <= 24:
            lines.append(f"<b>{esc(key)}:</b> {esc(value)}")
        else:
            lines.append(esc(line))
    return "\n".join(lines)


def alert_buttons(alert: Any) -> Buttons:
    """Next steps for an alert, so a phone notification is one tap from a fix."""
    rows: Buttons = []
    alert_id = str(alert.id)
    if alert_id.startswith("docker.") and alert.status != "recovered":
        container = alert_id.removeprefix("docker.").rsplit(".", 1)[0]
        if alert_id.endswith(".die"):
            rows.append([(f"▶️ Start {container}", f"c:/start {container}"), ("📜 Logs", f"c:/logs {container}")])
    if alert.severity in ("warning", "critical", "emergency") and alert.status in ("active", "event", "changed"):
        rows.append([("🔕 Silence 1h", "c:/silence 1h"), ("📋 Status", "c:/status")])
    return rows


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

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            response_text = getattr(getattr(exc, "response", None), "text", "")
            logging.error("Telegram %s failed: %s %s", method, redact(exc, self.bot_token), redact(response_text, self.bot_token))
            return None

    def _post_text(self, method: str, payload: dict[str, Any], text: str, html_mode: bool, buttons: Buttons | None) -> None:
        payload = {**payload, "text": text, "disable_web_page_preview": True}
        markup = keyboard(buttons)
        if markup:
            payload["reply_markup"] = markup
        if html_mode:
            payload["parse_mode"] = "HTML"
        if self._call(method, payload) is None and html_mode:
            # A formatting mistake must never cost an alert: retry once as plain text.
            payload.pop("parse_mode", None)
            payload["text"] = plain(text)
            self._call(method, payload)

    def send(self, text: str, force: bool = False, html: bool = False, buttons: Buttons | None = None) -> None:
        log_text = plain(text) if html else text
        if not self.enabled:
            logging.info("Telegram disabled, would send: %s", log_text.replace("\n", " | "))
            return

        if not force and self.state and silence_active(self.state):
            logging.info("Alerts silenced, skipped Telegram message: %s", log_text.replace("\n", " | "))
            return

        self._post_text("sendMessage", {"chat_id": self.chat_id}, text, html, buttons)

    def edit(self, message_id: Any, text: str, html: bool = True, buttons: Buttons | None = None) -> None:
        """Replace a message in place, for example a confirmation prompt with its result."""
        if not self.enabled:
            return
        self._post_text("editMessageText", {"chat_id": self.chat_id, "message_id": message_id}, text, html, buttons)

    def answer_callback(self, callback_id: Any, text: str | None = None) -> None:
        """Stop the spinner on a tapped button. Telegram shows `text` as a brief toast."""
        if not self.enabled:
            return
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text[:200]
        self._call("answerCallbackQuery", payload)

    def set_commands(self, commands: list[tuple[str, str]]) -> None:
        """Publish the command menu shown when you type / in the chat."""
        if not self.enabled:
            return
        payload = {"commands": [{"command": name.lstrip("/"), "description": description[:256]} for name, description in commands]}
        if self._call("setMyCommands", payload) is not None:
            logging.info("Telegram command menu updated with %s commands", len(commands))

    def send_alert(self, alert: Any, force: bool = False) -> None:
        icon, label = SEVERITY_LABELS.get(alert.severity, ("•", str(alert.severity).title()))
        if alert.status == "recovered":
            icon, label = "✅", "Recovered"
        elif alert.status == "changed" and alert.severity == "info":
            icon = "🔄"
        lines = [f"{icon} <b>{esc(alert.title)}</b>", f"<i>{esc(label)} · {esc(alert.source)}</i>"]
        if alert.body:
            lines += ["", f"<blockquote>{format_body(alert.body)}</blockquote>"]
        self.send("\n".join(lines), force=force, html=True, buttons=alert_buttons(alert))
