import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from monitors.api import GENERATED_TOKEN_KEY, resolve_action_token
from monitors.history import HistoryStore
from monitors.state import StateStore
from monitors.telegram import TelegramNotifier, redact


TOKEN = "123456789:AAH-fake_token-value"


class FakeState:
    def __init__(self) -> None:
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        return True


class RedactTests(unittest.TestCase):
    def test_redacts_token_inside_requests_error(self):
        message = (
            "HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded with url: "
            f"/bot{TOKEN}/getUpdates?timeout=25"
        )
        cleaned = redact(message)
        self.assertNotIn(TOKEN, cleaned)
        self.assertIn("/bot<redacted>/getUpdates", cleaned)

    def test_redacts_known_token_without_bot_prefix(self):
        self.assertNotIn(TOKEN, redact(f"token={TOKEN}", TOKEN))

    def test_leaves_normal_text_alone(self):
        self.assertEqual(redact("robot 42 is fine"), "robot 42 is fine")

    def test_send_failure_log_has_no_token(self):
        notifier = TelegramNotifier({"telegram": {"bot_token": TOKEN, "chat_id": "1"}})
        error = requests.ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/sendMessage")
        with patch("monitors.telegram.requests.post", side_effect=error), self.assertLogs(level="ERROR") as logs:
            notifier.send("hello", force=True)
        self.assertNotIn(TOKEN, "\n".join(logs.output))


class ActionTokenLoggingTests(unittest.TestCase):
    def test_generated_token_is_not_logged(self):
        state = FakeState()
        with patch.dict(os.environ, {}, clear=True), self.assertLogs(level="WARNING") as logs:
            token = resolve_action_token({}, state)
        self.assertEqual(state.get(GENERATED_TOKEN_KEY), token)
        self.assertNotIn(token, "\n".join(logs.output))


class PrivateFileTests(unittest.TestCase):
    def test_state_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = StateStore(str(path))
            store.set("api.action_token", "secret")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(StateStore(str(path)).get("api.action_token"), "secret")

    def test_history_db_is_owner_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            HistoryStore(str(path))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
