import json
import os
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from monitors.actions import ActionService
from monitors.alerts import Alert
from monitors.api import ApiServer
from monitors.power import AC_RECOVERY_TOKENS, CLASS_TOKEN_READ, CLASS_TOKEN_WRITE, DellSmbios, PowerService, power_supply
from monitors.telegram import TelegramNotifier, alert_buttons, keyboard, plain


class FakeBios(DellSmbios):
    """Token files on disk like the kernel's, and a BIOS that remembers one active mode."""

    def __init__(self, root: Path, offered=("off", "on"), active="off", write_result=0) -> None:
        tokens = root / "dell-smbios.0" / "tokens"
        tokens.mkdir(parents=True)
        for mode in offered:
            token_id = AC_RECOVERY_TOKENS[mode]
            # Real Dell WMI tokens use the token id as the location; values differ per mode.
            (tokens / f"{token_id:04x}_location").write_text(f"{token_id:08x}\n")
            (tokens / f"{token_id:04x}_value").write_text(f"{1 if mode == 'on' else 0:08x}\n")
        device = root / "dell-smbios"
        device.write_bytes(b"")
        super().__init__(device=device, token_glob=str(root / "dell-smbios.*" / "tokens"))
        self.active = active
        self.write_result = write_result
        self.calls = []

    def call(self, cmd_class, cmd_select, inputs):
        self.calls.append((cmd_class, cmd_select, tuple(inputs)))
        location = inputs[0]
        mode = next(mode for mode, token_id in AC_RECOVERY_TOKENS.items() if token_id == location)
        if cmd_class == CLASS_TOKEN_WRITE:
            if self.write_result == 0:
                self.active = mode
            return (self.write_result, 0, 0, 0)
        # The BIOS reports the stored value at the location: it equals the token's value only when that mode is active.
        token_value = 1 if mode == "on" else 0
        return (0, token_value if mode == self.active else token_value ^ 1, 0, 0)


class PowerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dmi = self.root / "dmi"
        self.dmi.mkdir()
        (self.dmi / "sys_vendor").write_text("Dell Inc.\n")
        (self.dmi / "product_name").write_text("Inspiron 15-3567\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def service(self, **kwargs) -> tuple[PowerService, FakeBios]:
        bios = FakeBios(self.root / "bios", **kwargs)
        return PowerService(smbios=bios, dmi_dir=self.dmi), bios


class PowerServiceTests(PowerTestCase):
    def test_reads_off_mode_and_offered_modes(self):
        service, bios = self.service(active="off")
        recovery = service.ac_recovery()
        self.assertEqual((recovery["supported"], recovery["mode"], recovery["modes"]), (True, "off", ["off", "on"]))
        self.assertTrue(all(call[0] == CLASS_TOKEN_READ for call in bios.calls))

    def test_reads_are_cached(self):
        service, bios = self.service()
        service.ac_recovery()
        count = len(bios.calls)
        service.ac_recovery()
        self.assertEqual(len(bios.calls), count)
        service.ac_recovery(fresh=True)
        self.assertGreater(len(bios.calls), count)

    def test_turning_on_writes_the_on_token_and_verifies(self):
        service, bios = self.service(active="off")
        result = service.set_ac_recovery("on")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["ac_recovery"]["mode"], "on")
        writes = [call for call in bios.calls if call[0] == CLASS_TOKEN_WRITE]
        self.assertEqual(writes, [(CLASS_TOKEN_WRITE, 0, (AC_RECOVERY_TOKENS["on"], 1))])

    def test_already_on_does_not_write(self):
        service, bios = self.service(active="on")
        result = service.set_ac_recovery("on")
        self.assertTrue(result["ok"])
        self.assertIn("already", result["message"])
        self.assertFalse([call for call in bios.calls if call[0] == CLASS_TOKEN_WRITE])

    def test_rejects_modes_the_bios_does_not_offer(self):
        service, _bios = self.service()
        self.assertIn("offers: off, on", service.set_ac_recovery("last")["error"])
        self.assertIn("mode must be", service.set_ac_recovery("sometimes")["error"])

    def test_bios_error_is_reported(self):
        service, _bios = self.service(write_result=-3)
        result = service.set_ac_recovery("on")
        self.assertFalse(result["ok"])
        self.assertIn("password", result["error"])

    def test_non_dell_is_unsupported_without_touching_devices(self):
        (self.dmi / "sys_vendor").write_text("LENOVO\n")
        service, bios = self.service()
        recovery = service.ac_recovery()
        self.assertFalse(recovery["supported"])
        self.assertIn("Dell", recovery["reason"])
        self.assertEqual(bios.calls, [])
        self.assertFalse(service.set_ac_recovery("on")["ok"])

    def test_missing_interface_is_unsupported(self):
        service, bios = self.service()
        bios.device.unlink()
        self.assertIn("dell-smbios", service.ac_recovery()["reason"])

    def test_permission_error_explains_privileges(self):
        service, bios = self.service()
        with patch.object(FakeBios, "token", side_effect=PermissionError("denied")):
            recovery = service.ac_recovery()
        self.assertFalse(recovery["supported"])
        self.assertIn("root", recovery["reason"])


class PowerSupplyTests(unittest.TestCase):
    def test_reads_mains_and_battery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, files in {"AC": {"type": "Mains", "online": "1"}, "BAT0": {"type": "Battery", "capacity": "37", "status": "Charging"}}.items():
                (root / name).mkdir()
                for key, value in files.items():
                    (root / name / key).write_text(value + "\n")
            with patch("monitors.power.POWER_SUPPLY_DIR", root):
                self.assertEqual(power_supply(), {"ac_online": True, "battery_percent": 37, "battery_status": "Charging"})

    def test_desktop_without_supplies(self):
        with patch("monitors.power.POWER_SUPPLY_DIR", Path("/nonexistent")):
            self.assertEqual(power_supply(), {"ac_online": None, "battery_percent": None, "battery_status": None})


class FakeHistory:
    def __init__(self) -> None:
        self.records = []

    def record(self, alert):
        self.records.append(alert)


class ActionTests(PowerTestCase):
    def test_action_records_history_and_respects_disabled_actions(self):
        service, _bios = self.service()
        history = FakeHistory()
        actions = ActionService({}, None, history, service)
        self.assertTrue(actions.set_ac_recovery("on")["ok"])
        self.assertEqual([record.id for record in history.records], ["power.ac_recovery"])

        disabled = ActionService({"actions": {"enabled": False}}, None, FakeHistory(), service)
        self.assertEqual(disabled.set_ac_recovery("off"), {"ok": False, "error": "actions are disabled"})


class FakeStatusService:
    def __init__(self) -> None:
        self.state = type("State", (), {"get": lambda self, key, default=None: default, "set": lambda self, key, value: True})()

    def power(self):
        return {"ac_online": True, "ac_recovery": {"supported": True, "mode": "off"}}

    status = health = network = docker = sites = power


class FakeActions:
    def __init__(self) -> None:
        self.modes = []

    def set_ac_recovery(self, mode):
        self.modes.append(mode)
        return {"ok": True, "message": f"Power on with AC set to {mode}"}


class ApiTests(unittest.TestCase):
    def test_power_routes(self):
        actions = FakeActions()
        with patch.dict(os.environ, {}, clear=True):
            server = ApiServer({"api": {"host": "127.0.0.1", "port": 0}}, FakeStatusService(), actions)
            server.start()
        try:
            host, port = server.server.server_address[:2]
            with urllib.request.urlopen(f"http://{host}:{port}/api/power", timeout=5) as response:
                self.assertEqual(json.loads(response.read())["ac_recovery"]["mode"], "off")
            request = urllib.request.Request(
                f"http://{host}:{port}/api/actions/power/ac-recovery",
                method="POST",
                data=b'{"mode": "on"}',
                headers={"X-Sheltie-Action-Token": server.action_token},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertTrue(json.loads(response.read())["ok"])
            self.assertEqual(actions.modes, ["on"])
        finally:
            server.stop()
            server.server.server_close()


class NotifierFormattingTests(unittest.TestCase):
    def alert(self, **overrides):
        values = {"id": "docker.blog.die", "source": "docker", "severity": "critical", "status": "event", "title": "Container <died>", "body": "Container: blog\nEvent: died & gone", "timestamp": ""}
        values.update(overrides)
        return Alert(**values)

    def test_alert_is_escaped_formatted_and_actionable(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_CHAT_ID": "42"}, clear=True):
            notifier = TelegramNotifier({})
        with patch.object(TelegramNotifier, "_call", return_value={"ok": True}) as call:
            notifier.send_alert(self.alert())
        method, payload = call.call_args.args
        self.assertEqual(method, "sendMessage")
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("Container &lt;died&gt;", payload["text"])
        self.assertIn("<b>Event:</b> died &amp; gone", payload["text"])
        data = [button["callback_data"] for row in payload["reply_markup"]["inline_keyboard"] for button in row]
        self.assertIn("c:/start blog", data)
        self.assertIn("c:/silence 1h", data)

    def test_html_failure_falls_back_to_plain_text(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_CHAT_ID": "42"}, clear=True):
            notifier = TelegramNotifier({})
        with patch.object(TelegramNotifier, "_call", side_effect=[None, {"ok": True}]) as call:
            notifier.send("<b>Hi</b> &amp; bye", html=True)
        fallback = call.call_args_list[1].args[1]
        self.assertNotIn("parse_mode", fallback)
        self.assertEqual(fallback["text"], "Hi & bye")

    def test_recovered_alert_has_no_silence_button(self):
        self.assertEqual(alert_buttons(self.alert(id="cpu.high", status="recovered", severity="info")), [])

    def test_keyboard_drops_oversized_callback_data(self):
        self.assertIsNone(keyboard([[("x", "c:/logs " + "a" * 80)]]))
        self.assertEqual(plain("<i>a</i> &lt;b&gt;"), "a <b>")


if __name__ == "__main__":
    unittest.main()
