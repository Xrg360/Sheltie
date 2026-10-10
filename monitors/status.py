import time
from datetime import datetime, timezone
from typing import Any

import docker
import psutil

from monitors import __version__
from monitors.alerts import SILENCED_UNTIL_KEY, silence_active
from monitors.autofix import USER_STOPPED_KEY
from monitors.network import get_default_route, get_interface_status
from monitors.temp import read_cpu_temperature


class StatusService:
    def __init__(self, config: dict[str, Any], state: Any, history: Any, notifier: Any = None) -> None:
        self.config = config
        self.state = state
        self.history = history
        self.notifier = notifier
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._started_monotonic = time.monotonic()
        self._last_cycle_monotonic: float | None = None
        self.last_cycle_at: str | None = None

    def mark_cycle(self) -> None:
        """Called by the main loop after every round of checks."""
        self._last_cycle_monotonic = time.monotonic()
        self.last_cycle_at = datetime.now(timezone.utc).isoformat()

    def liveness(self) -> dict[str, Any]:
        """Healthy while the check loop keeps completing. Used by the Docker healthcheck."""
        interval = int(self.config.get("interval", 30) or 30)
        limit = max(90, interval * 3)
        since = self._last_cycle_monotonic if self._last_cycle_monotonic is not None else self._started_monotonic
        age = time.monotonic() - since
        return {
            "ok": age <= limit,
            "version": __version__,
            "started_at": self.started_at,
            "last_cycle_at": self.last_cycle_at,
            "seconds_since_last_cycle": round(age, 1),
            "limit_seconds": limit,
        }

    def status(self) -> dict[str, Any]:
        route = self.state.get("changes.network.route.value")
        return {
            "version": __version__,
            "started_at": self.started_at,
            "telegram_enabled": bool(getattr(self.notifier, "enabled", False)),
            "alerts_silenced": silence_active(self.state),
            "alerts_silenced_until": self.state.get(SILENCED_UNTIL_KEY),
            "internet_up": self.state.get("internet.up"),
            "ethernet_up": self.state.get("changes.network.ethernet.value"),
            "wifi_up": self.state.get("changes.network.wifi.value"),
            "default_route": route,
            "default_route_label": self.route_label(route),
            "auto_heal": {
                "enabled": bool((self.config.get("auto_heal", {}) or {}).get("enabled", True)),
                "interval": (self.config.get("auto_heal", {}) or {}).get("interval", 300),
                "active_containers": self.state.get("auto_heal.containers.active", []),
                "active_network_interfaces": self.state.get("auto_heal.network.active", []),
            },
            "active_alerts": self.active_alerts(),
            "recent_events": self.history.recent(20),
        }

    def health(self) -> dict[str, Any]:
        disk_path = ((self.config.get("disk", {}) or {}).get("paths") or ["/"])[0]
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_path": disk_path,
            "disk_percent": psutil.disk_usage(disk_path).percent,
            "cpu_temperature": read_cpu_temperature(),
            "load_average": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
        }

    def network(self) -> dict[str, Any]:
        network_config = self.config.get("network", {}) or {}
        interfaces = {}
        for label in ("ethernet", "wifi"):
            name = network_config.get(label)
            if not name:
                continue
            status = get_interface_status(name)
            interfaces[label] = {
                "name": status.name,
                "operstate": status.operstate,
                "carrier": status.carrier,
                "has_ip": status.has_ip,
                "up": status.up,
            }
        route = get_default_route()
        return {
            "interfaces": interfaces,
            "default_route": route,
            "default_route_label": self.route_label(route),
            "internet_up": self.state.get("internet.up"),
        }

    def docker(self) -> dict[str, Any]:
        action_config = self.config.get("actions", {}) or {}
        blocked = set(action_config.get("blocked_containers") or ["sheltie", "meerkat"])
        user_stopped = set(self.state.get(USER_STOPPED_KEY, []))
        tracked = set(self.state.get("auto_heal.containers.active", []))
        try:
            client = docker.from_env()
            containers = [
                {
                    "name": container.name,
                    "status": container.status,
                    "image": ",".join(container.image.tags),
                    "blocked": container.name in blocked,
                    "user_stopped": container.name in user_stopped,
                    "auto_heal_tracked": container.name in tracked,
                }
                for container in client.containers.list(all=True)
            ]
        except Exception as exc:
            return {"available": False, "error": str(exc), "containers": []}
        return {"available": True, "containers": containers}

    def sites(self) -> dict[str, Any]:
        sites = self.state.get("sites.status", [])
        return {
            "total": len(sites),
            "up": len([site for site in sites if site.get("up") is True]),
            "down": len([site for site in sites if site.get("up") is False]),
            "sites": sites,
        }

    def active_alerts(self) -> list[str]:
        prefix = "alerts."
        suffix = ".notified"
        active = []
        for key, value in self.state.snapshot().items():
            if key.startswith(prefix) and key.endswith(suffix) and value is True:
                active.append(key.removeprefix(prefix).removesuffix(suffix))
        return sorted(active)

    def route_label(self, route: str | None) -> str:
        if not route:
            return "unknown"
        network_config = self.config.get("network", {}) or {}
        if route == network_config.get("ethernet"):
            return f"wired/eth ({route})"
        if route == network_config.get("wifi"):
            return f"wifi ({route})"
        return f"other ({route})"
