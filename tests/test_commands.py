import time
import unittest
from unittest.mock import patch

import docker

from monitors.alerts import SILENCED_KEY
from monitors.autofix import USER_STOPPED_KEY
from monitors.commands import COMMANDS, HELP_TEXT, MAX_LOG_LINES, MAX_MESSAGE_CHARS, TelegramCommandMonitor, clamp_count, confirm_data, human_duration, tail_text
from monitors.internet import ping_stats


TOKEN = "123456789:AAH-fake_token-value"


class FakeState:
    def __init__(self) -> None:
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        return True


class FakeNotifier:
    enabled = True
    chat_id = "42"
    bot_token = TOKEN

    def __init__(self) -> None:
        self.sent = []
        self.buttons = []
        self.edits = []
        self.answers = []

    def send(self, text, force=False, html=False, buttons=None):
        self.sent.append(text)
        self.buttons.append(buttons or [])

    def edit(self, message_id, text, html=True, buttons=None):
        self.edits.append((message_id, text, buttons or []))

    def answer_callback(self, callback_id, text=None):
        self.answers.append((callback_id, text))


class FakeHistory:
    def __init__(self, events=None) -> None:
        self.events = events or []
        self.limits = []

    def recent(self, limit=50):
        self.limits.append(limit)
        return self.events[:limit]


class FakeStatus:
    def __init__(self, state) -> None:
        self.state = state
        self.history = FakeHistory([{"ts": "2026-10-10T07:00:00+00:00", "status": "active", "title": "Site down: Portfolio"}])
        self.log_requests = []

    def active_alerts(self):
        return ["site.portfolio.down"]

    def status(self):
        return {"started_at": "2026-10-10T07:00:00+00:00"}

    def container_logs(self, name, lines):
        self.log_requests.append((name, lines))
        if name == "missing":
            raise docker.errors.NotFound("No such container: missing")
        return f"connecting to https://api.telegram.org/bot{TOKEN}/getMe\nready\n"

    def container_stats(self, name=None):
        rows = [
            {"name": "web", "cpu_percent": 2.0, "memory_used": 50 * 1024**2, "memory_limit": 0, "memory_percent": None},
            {"name": "db", "cpu_percent": 9.5, "memory_used": 200 * 1024**2, "memory_limit": 512 * 1024**2, "memory_percent": 39.1},
        ]
        return [row for row in rows if name in (None, row["name"])]

    def host(self):
        return {
            "uptime_seconds": 90000,
            "sheltie_uptime_seconds": 120,
            "load_average": (0.5, 0.4, 0.3),
            "cpu_count": 4,
            "swap_percent": 40.0,
            "swap_used": 1.5 * 1024**3,
            "swap_total": 3.7 * 1024**3,
        }

    def disks(self):
        return [{"path": "/", "percent": 31.0, "used": 29 * 1024**3, "total": 98 * 1024**3, "free": 65 * 1024**3}]

    def addresses(self):
        return {"enp2s0": ["192.168.1.80"], "tailscale0": ["100.64.0.1"]}

    def docker(self):
        return {
            "available": True,
            "containers": [
                {"name": "web", "status": "running"},
                {"name": "<blog>", "status": "exited"},
                {"name": "sheltie", "status": "running", "blocked": True},
            ],
        }

    def power(self):
        return {
            "vendor": "Dell Inc.",
            "model": "Inspiron 15-3567",
            "ac_online": True,
            "battery_percent": 37,
            "battery_status": "Charging",
            "ac_recovery": dict(self.recovery),
        }

    recovery = {"supported": True, "mode": "off", "modes": ["off", "on"], "reason": None}


class FakeActions:
    def __init__(self) -> None:
        self.calls = []

    def _ok(self, name, *args):
        self.calls.append((name, *args))
        return {"ok": True, "message": f"{name} done"}

    def start_container(self, name):
        return self._ok("start", name)

    def stop_container(self, name):
        if name == "sheltie":
            return {"ok": False, "error": "container stop is blocked: sheltie"}
        return self._ok("stop", name)

    def restart_container(self, name):
        return self._ok("restart", name)

    def silence_alerts(self, minutes=None):
        return self._ok("silence", minutes)

    def resume_alerts(self):
        return self._ok("resume")

    def set_ac_recovery(self, mode):
        self.calls.append(("ac_recovery", mode))
        recovery = {"supported": True, "mode": mode, "modes": ["off", "on"], "reason": None}
        return {"ok": True, "message": f"Power on with AC set to {mode}", "ac_recovery": recovery}


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.state = FakeState()
        self.notifier = FakeNotifier()
        self.status = FakeStatus(self.state)
        self.actions = FakeActions()
        config = {"sites": [{"name": "Cloudflare DNS", "url": "https://1.1.1.1"}]}
        self.monitor = TelegramCommandMonitor(config, self.state, self.notifier, self.status, self.actions)

    def send(self, text, age=1):
        self.monitor._handle_update({"message": {"chat": {"id": 42}, "text": text, "date": int(time.time() - age)}})
        return self.notifier.sent[-1] if self.notifier.sent else None

    def test_help_lists_new_commands(self):
        reply = self.send("/help")
        for command in ("/alerts", "/events", "/logs", "/stats", "/stop", "/uptime", "/disk", "/ip", "/ping", "/checksite", "/version"):
            self.assertIn(command, reply)

    def test_bare_start_is_a_welcome_not_an_action(self):
        self.assertIn("Sheltie", self.send("/start"))
        self.assertEqual(self.actions.calls, [])
        self.assertTrue(self.notifier.buttons[-1], "welcome offers the menu buttons")

    def test_start_container_clears_user_stopped_mark(self):
        self.state.set(USER_STOPPED_KEY, ["web", "db"])
        self.assertIn("started", self.send("/start web"))
        self.assertEqual(self.actions.calls, [("start", "web")])
        self.assertEqual(self.state.get(USER_STOPPED_KEY), ["db"])

    def test_stop_respects_blocked_containers(self):
        self.assertIn("blocked", self.send("/stop sheltie"))
        self.assertIn("stopped", self.send("/stop web"))
        self.assertEqual(self.actions.calls, [("stop", "web")])

    def test_stale_container_commands_are_ignored(self):
        reply = self.send("/stop web", age=3600)
        self.assertIn("Ignored /stop", reply)
        self.send("/start web", age=3600)
        self.assertEqual(self.actions.calls, [])

    def test_stale_bare_start_is_dropped_silently(self):
        self.assertIsNone(self.send("/start", age=3600))

    def test_silence_with_duration_goes_through_actions(self):
        reply = self.send("/silence 2h")
        self.assertEqual(self.actions.calls, [("silence", 120.0)])
        self.assertIn("2h", reply)

    def test_silence_rejects_bad_duration(self):
        self.assertIn("Usage", self.send("/silence soon"))
        self.assertEqual(self.actions.calls, [])

    def test_resume_goes_through_actions(self):
        self.send("/resume")
        self.assertEqual(self.actions.calls, [("resume",)])

    def test_alerts_show_firing_time(self):
        self.state.set("alerts.site.portfolio.down.active_since", time.time() - 7200)
        self.state.set(SILENCED_KEY, True)
        reply = self.send("/alerts")
        self.assertIn("site.portfolio.down - firing for 2h", reply)
        self.assertIn("silenced", reply)

    def test_events_count_is_clamped(self):
        self.send("/events 500")
        self.send("/events abc")
        self.assertEqual(self.status.history.limits, [30, 10])

    def test_logs_are_redacted_and_clamped(self):
        reply = self.send("/logs web 1000")
        self.assertNotIn(TOKEN, reply)
        self.assertIn("ready", reply)
        self.assertEqual(self.status.log_requests, [("web", MAX_LOG_LINES)])

    def test_logs_for_unknown_container_reports_error(self):
        self.assertIn("No container called missing", self.send("/logs missing"))

    def test_stats_sorted_by_cpu(self):
        reply = self.send("/stats")
        self.assertLess(reply.index("db"), reply.index("web"))
        self.assertIn("39%", reply)

    def test_uptime_and_disk(self):
        self.assertIn("Host: 1d 1h", self.send("/uptime"))
        self.assertIn("31% /", self.send("/disk"))

    def test_ip_lists_interfaces_and_public_ip(self):
        with patch("monitors.commands.public_ip", return_value="203.0.113.7"):
            reply = self.send("/ip")
        self.assertIn("192.168.1.80", reply)
        self.assertIn("203.0.113.7", reply)

    def test_ping_rejects_option_injection(self):
        self.assertIn("not a valid", self.send("/ping -f"))

    def test_checksite_runs_a_probe(self):
        result = {"name": "Cloudflare DNS", "url": "https://1.1.1.1", "up": True, "status_code": 200, "latency_ms": 12, "error": None, "expected_status": [200]}
        with patch("monitors.commands.probe_site", return_value=result) as probe:
            reply = self.send('/checksite "cloudflare dns"')
        probe.assert_called_once()
        self.assertIn("is up", reply)

    def test_checksite_unknown_name_lists_sites(self):
        self.assertIn("Cloudflare DNS", self.send("/checksite nope"))

    def test_version(self):
        self.assertIn("Sheltie", self.send("/version"))

    def test_handler_errors_are_reported_without_token(self):
        with patch.object(FakeStatus, "host", side_effect=RuntimeError(f"bad /bot{TOKEN}/x")), self.assertLogs(level="ERROR"):
            reply = self.send("/uptime")
        self.assertIn("/uptime failed", reply)
        self.assertNotIn(TOKEN, reply)


    def press(self, data, chat_id=42, message_id=7):
        self.monitor._handle_update(
            {"callback_query": {"id": "cb1", "data": data, "message": {"message_id": message_id, "chat": {"id": chat_id}}}}
        )

    def all_button_data(self):
        return [data for row in self.notifier.buttons[-1] for _label, data in row]

    def test_help_and_menu_cover_power_commands(self):
        reply = self.send("/help")
        for command in ("/power", "/autoon", "/menu", "/heal"):
            self.assertIn(command, reply)
        self.assertEqual(HELP_TEXT, reply)
        self.assertEqual(len({command for command, *_ in COMMANDS}), len(COMMANDS))
        self.send("/menu")
        self.assertIn("c:/power", self.all_button_data())

    def test_power_shows_off_with_turn_on_button(self):
        reply = self.send("/power")
        self.assertIn("Power on with AC: off", reply)
        self.assertIn("battery 37%", reply)
        self.assertIn("c:/autoon on", self.all_button_data())
        self.assertEqual(self.actions.calls, [])

    def test_battery_alias_and_bare_autoon_only_show(self):
        self.assertIn("Power on with AC", self.send("/battery"))
        self.assertIn("Power on with AC", self.send("/autoon"))
        self.assertEqual(self.actions.calls, [])

    def test_autoon_on_changes_the_setting(self):
        reply = self.send("/autoon on")
        self.assertEqual(self.actions.calls, [("ac_recovery", "on")])
        self.assertIn("Power on with AC: on", reply)

    def test_autoon_rejects_unknown_mode(self):
        self.assertIn("Usage", self.send("/autoon sometimes"))
        self.assertEqual(self.actions.calls, [])

    def test_stale_autoon_is_ignored(self):
        self.assertIn("Ignored /autoon", self.send("/autoon on", age=3600))
        self.assertEqual(self.actions.calls, [])

    def test_unsupported_power_explains_why(self):
        with patch.object(FakeStatus, "recovery", {"supported": False, "mode": None, "modes": [], "reason": "Only Dell BIOS settings are supported so far"}):
            reply = self.send("/power")
        self.assertIn("not available", reply)
        self.assertIn("Only Dell", reply)
        self.assertNotIn("c:/autoon on", self.all_button_data())

    def test_status_survives_missing_sections(self):
        reply = self.send("/status")
        self.assertIn("problem", reply)
        self.assertIn("Power on with AC: off", reply)

    def test_navigation_button_runs_read_only_command(self):
        self.press("c:/uptime")
        self.assertEqual(self.notifier.answers, [("cb1", None)])
        self.assertIn("Host: 1d 1h", self.notifier.sent[-1])

    def test_disruptive_button_asks_before_acting(self):
        self.press("c:/autoon on")
        self.assertEqual(self.actions.calls, [])
        self.assertIn("Turn on power on with AC?", self.notifier.sent[-1])
        yes = self.all_button_data()[0]
        self.assertTrue(yes.startswith("y:"))
        self.assertIn("n", self.all_button_data())

        self.press(yes)
        self.assertEqual(self.actions.calls, [("ac_recovery", "on")])
        message_id, text, _buttons = self.notifier.edits[-1]
        self.assertEqual(message_id, 7)
        self.assertIn("Power on with AC set to on", text)

    def test_restart_button_confirms_and_typed_restart_does_not(self):
        self.press("c:/restart web")
        self.assertEqual(self.actions.calls, [])
        self.send("/restart web")
        self.assertEqual(self.actions.calls, [("restart", "web")])

    def test_expired_confirmation_does_nothing(self):
        self.press(confirm_data("/stop web", now=time.time() - 3600))
        self.assertEqual(self.actions.calls, [])
        self.assertIn("expired", self.notifier.edits[-1][1])

    def test_cancel_button_edits_the_prompt(self):
        self.press("n")
        self.assertIn("Cancelled", self.notifier.edits[-1][1])
        self.assertEqual(self.actions.calls, [])

    def test_buttons_from_other_chats_are_ignored(self):
        with self.assertLogs(level="INFO"):
            self.press(confirm_data("/stop web"), chat_id=99)
        self.assertEqual(self.actions.calls, [])
        self.assertEqual(self.notifier.sent, [])

    def test_bare_restart_offers_a_picker_without_blocked_containers(self):
        reply = self.send("/restart")
        data = self.all_button_data()
        self.assertIn("Restart which container", reply)
        self.assertEqual(data, ["c:/restart web"])
        self.assertEqual(self.actions.calls, [])

    def test_docker_escapes_names_and_offers_start(self):
        reply = self.send("/docker")
        self.assertIn("&lt;blog&gt;", reply)
        self.assertNotIn("<blog>", reply)
        self.assertIn("c:/start <blog>", self.all_button_data())

    def test_logs_are_wrapped_and_escaped(self):
        reply = self.send("/logs web")
        self.assertIn("<pre>", reply)
        self.assertLessEqual(len(reply), 4096)


class HelperTests(unittest.TestCase):
    def test_clamp_count(self):
        self.assertEqual(clamp_count(None, 10, 30), 10)
        self.assertEqual(clamp_count("0", 10, 30), 1)
        self.assertEqual(clamp_count("99", 10, 30), 30)

    def test_tail_text_keeps_newest_lines(self):
        text = "old\n" * 2000 + "newest"
        trimmed = tail_text(text)
        self.assertLessEqual(len(trimmed), MAX_MESSAGE_CHARS)
        self.assertTrue(trimmed.endswith("newest"))

    def test_human_duration(self):
        self.assertEqual(human_duration(45), "45s")
        self.assertEqual(human_duration(3700), "1h 1m")
        self.assertEqual(human_duration(90000), "1d 1h")

    def test_ping_stats_parses_linux_output(self):
        output = (
            "3 packets transmitted, 3 received, 0% packet loss, time 2003ms\n"
            "rtt min/avg/max/mdev = 10.1/12.5/15.0/2.0 ms\n"
        )
        completed = type("Done", (), {"returncode": 0, "stdout": output, "stderr": ""})()
        with patch("monitors.internet.subprocess.run", return_value=completed):
            stats = ping_stats("1.1.1.1")
        self.assertEqual((stats["avg_ms"], stats["loss_percent"]), (12.5, 0.0))


if __name__ == "__main__":
    unittest.main()
