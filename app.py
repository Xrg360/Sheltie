import logging
import signal
import sys
import time
from pathlib import Path
from threading import Event
from typing import Any

import yaml

from monitors.actions import ActionService
from monitors.alerts import AlertManager
from monitors.api import ApiServer
from monitors.autofix import AutoHealMonitor
from monitors.commands import TelegramCommandMonitor
from monitors.config import validate_config
from monitors.cpu import check_cpu
from monitors.disk import check_disk
from monitors.docker import DockerEventMonitor
from monitors.history import HistoryStore
from monitors.internet import check_internet
from monitors.network import check_network
from monitors.power import PowerService
from monitors.ram import check_ram
from monitors.sites import check_sites
from monitors.state import StateStore
from monitors.status import StatusService
from monitors.telegram import TelegramNotifier
from monitors.temp import check_temperature


CONFIG_PATH = Path("config/config.yml")
STATE_PATH = Path("state/state.json")
HISTORY_PATH = Path("state/history.db")
BOOT_NOTICE_KEY = "sheltie.boot_notice_at"
BOOT_NOTICE_INTERVAL = 600


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing configuration file: {CONFIG_PATH}")

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def run_check(name: str, callback: Any, config: dict[str, Any], state: StateStore, alerts: AlertManager) -> None:
    try:
        callback(config, state, alerts)
    except Exception:
        logging.exception("%s check failed", name)


def announce_boot(state: StateStore, alerts: AlertManager) -> None:
    # A crash loop restarts the container every few seconds. One boot message per
    # BOOT_NOTICE_INTERVAL is enough; the rest would flood the chat.
    now = time.time()
    last = float(state.get(BOOT_NOTICE_KEY) or 0)
    if now - last < BOOT_NOTICE_INTERVAL:
        logging.warning("Sheltie restarted again within %ss; boot message not sent", BOOT_NOTICE_INTERVAL)
        return
    state.set(BOOT_NOTICE_KEY, now)
    alerts.event(
        alert_id="sheltie.boot",
        source="sheltie",
        severity="info",
        title="Sheltie booted",
        body="Docker container started and monitoring is active.",
        force=True,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = load_config()
    validate_config(config)
    interval = int(config.get("interval", 30))
    state = StateStore(str(STATE_PATH))
    history = HistoryStore(str(HISTORY_PATH))
    notifier = TelegramNotifier(config, state)
    alerts = AlertManager(config, state, notifier, history)
    power = PowerService()
    action_service = ActionService(config, state, history, power)
    status_service = StatusService(config, state, history, notifier, power)
    stopped = Event()

    auto_heal_monitor = AutoHealMonitor(config, state, alerts, action_service)
    auto_heal_monitor.start()
    docker_monitor = DockerEventMonitor(state, alerts, ignored_containers=action_service.blocked_containers)
    docker_monitor.start()
    command_monitor = TelegramCommandMonitor(config, state, notifier, status_service, action_service)
    command_monitor.start()
    api_server = ApiServer(config, status_service, action_service)
    api_server.start()

    def handle_signal(signum: int, _frame: Any) -> None:
        logging.info("Received signal %s, shutting down", signum)
        stopped.set()
        auto_heal_monitor.stop()
        docker_monitor.stop()
        command_monitor.stop()
        api_server.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logging.info("Sheltie started with %ss interval", interval)
    announce_boot(state, alerts)

    checks = [
        ("network", check_network),
        ("internet", check_internet),
        ("cpu", check_cpu),
        ("ram", check_ram),
        ("disk", check_disk),
        ("temperature", check_temperature),
        ("sites", check_sites),
    ]

    while not stopped.is_set():
        for name, callback in checks:
            run_check(name, callback, config, state, alerts)
        status_service.mark_cycle()

        stopped.wait(interval)

    logging.info("Sheltie stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
