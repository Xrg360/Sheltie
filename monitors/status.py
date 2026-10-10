import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import docker
import psutil

from monitors import __version__
from monitors.alerts import SILENCED_UNTIL_KEY, silence_active
from monitors.autofix import USER_STOPPED_KEY
from monitors.network import get_default_route, get_interface_status
from monitors.power import PowerService
from monitors.temp import read_cpu_temperature


def _container_usage(container: Any) -> dict[str, Any]:
    try:
        stats = container.stats(stream=False)
    except Exception as exc:
        return {"name": container.name, "error": str(exc)}

    cpu = stats.get("cpu_stats") or {}
    precpu = stats.get("precpu_stats") or {}
    cpu_delta = (cpu.get("cpu_usage") or {}).get("total_usage", 0) - (precpu.get("cpu_usage") or {}).get("total_usage", 0)
    system_delta = (cpu.get("system_cpu_usage") or 0) - (precpu.get("system_cpu_usage") or 0)
    cpus = cpu.get("online_cpus") or len((cpu.get("cpu_usage") or {}).get("percpu_usage") or []) or 1
    cpu_percent = cpu_delta / system_delta * cpus * 100 if cpu_delta > 0 and system_delta > 0 else 0.0

    memory = stats.get("memory_stats") or {}
    # Match `docker stats`: page cache that can be dropped is not counted as used.
    cache = (memory.get("stats") or {}).get("inactive_file", 0)
    used = max(0, (memory.get("usage") or 0) - cache)
    limit = memory.get("limit") or 0
    return {
        "name": container.name,
        "cpu_percent": round(cpu_percent, 1),
        "memory_used": used,
        "memory_limit": limit,
        "memory_percent": round(used / limit * 100, 1) if limit else None,
    }


class StatusService:
    def __init__(self, config: dict[str, Any], state: Any, history: Any, notifier: Any = None, power: Any = None) -> None:
        self.config = config
        self.state = state
        self.history = history
        self.notifier = notifier
        self.power_service = power or PowerService()
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

    def container_logs(self, name: str, lines: int) -> str:
        client = docker.from_env()
        output = client.containers.get(name).logs(tail=lines, timestamps=False)
        return output.decode("utf-8", errors="replace")

    def container_stats(self, name: str | None = None) -> list[dict[str, Any]]:
        """CPU and memory per running container (one sample each, taken in parallel)."""
        client = docker.from_env()
        if name:
            containers = [client.containers.get(name)]
        else:
            containers = client.containers.list()
        if not containers:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(containers))) as pool:
            return list(pool.map(_container_usage, containers))

    def host(self) -> dict[str, Any]:
        swap = psutil.swap_memory()
        return {
            "boot_time": psutil.boot_time(),
            "uptime_seconds": time.time() - psutil.boot_time(),
            "sheltie_uptime_seconds": time.monotonic() - self._started_monotonic,
            "load_average": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
            "cpu_count": psutil.cpu_count(),
            "swap_percent": swap.percent,
            "swap_used": swap.used,
            "swap_total": swap.total,
        }

    def power(self) -> dict[str, Any]:
        return self.power_service.status()

    def disks(self) -> list[dict[str, Any]]:
        paths = (self.config.get("disk", {}) or {}).get("paths") or ["/"]
        result = []
        for path in paths:
            try:
                usage = psutil.disk_usage(path)
            except OSError as exc:
                result.append({"path": path, "error": str(exc)})
                continue
            result.append({"path": path, "percent": usage.percent, "used": usage.used, "total": usage.total, "free": usage.free})
        return result

    def addresses(self) -> dict[str, list[str]]:
        """IPv4 addresses per interface, skipping loopback and Docker's virtual interfaces."""
        skipped = ("lo", "docker", "veth", "br-")
        addresses: dict[str, list[str]] = {}
        for interface, entries in psutil.net_if_addrs().items():
            if interface.startswith(skipped):
                continue
            ips = [entry.address for entry in entries if entry.family == socket.AF_INET]
            if ips:
                addresses[interface] = ips
        return addresses

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
