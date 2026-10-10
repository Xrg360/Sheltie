import time
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

import app
from monitors.autofix import AutoHealMonitor
from monitors.docker import DockerEventMonitor
from monitors.status import StatusService


class FakeState:
    def __init__(self) -> None:
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        return True

    def snapshot(self):
        return dict(self.data)


class FakeAlerts:
    def __init__(self) -> None:
        self.events = []

    def event(self, **kwargs):
        self.events.append(kwargs)


class FakeActions:
    blocked_containers = {"sheltie"}

    def __init__(self) -> None:
        self.started = []

    def start_container(self, name):
        self.started.append(name)
        return {"ok": True, "message": f"started {name}"}


@dataclass
class Container:
    name: str
    status: str
    exit_code: int = 1
    labels: dict = field(default_factory=dict)

    @property
    def attrs(self):
        return {"State": {"ExitCode": self.exit_code}}


class LivenessTests(unittest.TestCase):
    def test_healthy_after_a_recent_cycle(self):
        service = StatusService({"interval": 30}, FakeState(), history=None)
        service.mark_cycle()
        liveness = service.liveness()
        self.assertTrue(liveness["ok"])
        self.assertIsNotNone(liveness["last_cycle_at"])

    def test_unhealthy_when_loop_stalls(self):
        service = StatusService({"interval": 30}, FakeState(), history=None)
        service.mark_cycle()
        with patch("monitors.status.time.monotonic", return_value=time.monotonic() + 3600):
            self.assertFalse(service.liveness()["ok"])

    def test_healthy_during_startup_grace(self):
        service = StatusService({"interval": 30}, FakeState(), history=None)
        self.assertTrue(service.liveness()["ok"])


class BootNoticeTests(unittest.TestCase):
    def test_only_one_boot_message_per_window(self):
        state, alerts = FakeState(), FakeAlerts()
        app.announce_boot(state, alerts)
        with self.assertLogs(level="WARNING"):
            app.announce_boot(state, alerts)
        self.assertEqual(len(alerts.events), 1)

    def test_boot_message_after_window(self):
        state, alerts = FakeState(), FakeAlerts()
        state.set(app.BOOT_NOTICE_KEY, time.time() - app.BOOT_NOTICE_INTERVAL - 1)
        app.announce_boot(state, alerts)
        self.assertEqual(len(alerts.events), 1)


class AutoHealSafetyTests(unittest.TestCase):
    def heal(self, *containers):
        state, actions = FakeState(), FakeActions()
        state.set("auto_heal.containers.active", [container.name for container in containers])
        monitor = AutoHealMonitor({"auto_heal": {"repair_cooldown": 0}}, state, FakeAlerts(), actions)
        with patch("monitors.autofix.docker.from_env") as docker_from_env:
            docker_from_env.return_value.containers.list.return_value = list(containers)
            monitor._heal_containers()
        return actions.started

    def test_crashed_container_is_started(self):
        self.assertEqual(self.heal(Container("web", "exited", exit_code=137)), ["web"])

    def test_finished_one_shot_job_is_left_alone(self):
        self.assertEqual(self.heal(Container("migrate", "exited", exit_code=0)), [])

    def test_label_opts_out(self):
        self.assertEqual(self.heal(Container("web", "exited", labels={"sheltie.autoheal": "false"})), [])


class DockerEventIgnoreTests(unittest.TestCase):
    def test_uses_configured_blocked_containers(self):
        alerts = FakeAlerts()
        monitor = DockerEventMonitor(FakeState(), alerts, ignored_containers={"noisy"})
        for name in ("noisy", "web"):
            monitor._handle_event({"Action": "start", "Actor": {"ID": name, "Attributes": {"name": name}}, "time": 0})
        self.assertEqual([event["title"] for event in alerts.events], ["Container started"])
        self.assertIn("web", alerts.events[0]["body"])


if __name__ == "__main__":
    unittest.main()
