import platform
import re
import shutil
import subprocess
import time
from urllib.parse import urlparse
from typing import Any

from monitors.alerts import SEVERITY_ORDER, clear_silence, parse_duration, set_silence


# Site names end up in Telegram messages, Prometheus labels and HTML, so keep them plain.
SITE_NAME_PATTERN = re.compile(r"^[\w .()-]{1,64}$")
MAX_SITE_TIMEOUT = 60.0


def normalize_site(site: dict[str, Any]) -> dict[str, Any]:
    """Validate a runtime site monitor and return the stored form. Raises ValueError with a readable message."""
    name = str(site.get("name") or "").strip()
    if not name:
        raise ValueError("site name is required")
    if not SITE_NAME_PATTERN.match(name):
        raise ValueError("site name may only use letters, numbers, spaces and . _ - ( ), up to 64 characters")

    url = str(site.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("site URL must start with http:// or https://")
    if len(url) > 2048 or any(ch.isspace() for ch in url):
        raise ValueError("site URL must be a single line up to 2048 characters")

    raw_status = site.get("expected_status") or [200]
    if not isinstance(raw_status, list):
        raw_status = [raw_status]
    expected_status = []
    for code in raw_status:
        try:
            value = int(str(code).strip())
        except ValueError:
            raise ValueError("expected_status must be HTTP status codes such as 200") from None
        if not 100 <= value <= 599:
            raise ValueError("expected_status codes must be between 100 and 599")
        expected_status.append(value)

    try:
        timeout = float(site.get("timeout", 10))
    except (TypeError, ValueError):
        raise ValueError("timeout must be a number of seconds") from None
    if not 0 < timeout <= MAX_SITE_TIMEOUT:
        raise ValueError(f"timeout must be greater than 0 and at most {MAX_SITE_TIMEOUT:g} seconds")

    severity = str(site.get("severity") or "critical").lower()
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"severity must be one of: {', '.join(SEVERITY_ORDER)}")

    normalized: dict[str, Any] = {
        "name": name,
        "url": url,
        "expected_status": expected_status,
        "timeout": timeout,
        "follow_redirects": bool(site.get("follow_redirects", True)),
        "severity": severity,
    }
    for field, default in (("duration", "30s"), ("cooldown", "15m")):
        value = site.get(field, default)
        try:
            if parse_duration(value) < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"{field} must be a duration such as 30s, 5m or 1h") from None
        normalized[field] = value

    keyword = str(site.get("keyword") or "").strip()
    if keyword:
        normalized["keyword"] = keyword[:256]
    return normalized


class ActionService:
    def __init__(self, config: dict[str, Any], state: Any, history: Any) -> None:
        self.config = config
        self.state = state
        self.history = history
        action_config = config.get("actions", {}) or {}
        self.enabled = bool(action_config.get("enabled", True))
        self.blocked_containers = set(action_config.get("blocked_containers") or ["sheltie", "meerkat"])

    def clear_ram_cache(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "actions are disabled"}
        if platform.system().lower() != "linux":
            return {"ok": False, "error": "clear RAM cache is only supported on Linux"}

        try:
            subprocess.run(["sync"], check=True, timeout=10)
            subprocess.run(
                ["sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"],
                check=True,
                timeout=10,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            return {"ok": False, "error": (exc.stderr or str(exc)).strip()}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)}

        return {"ok": True, "message": "Linux page cache, dentries, and inodes were dropped"}

    def restart_container(self, name: str) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "actions are disabled"}
        name = name.strip()
        if not name:
            return {"ok": False, "error": "container name is required"}
        if name in self.blocked_containers:
            return {"ok": False, "error": f"container restart is blocked: {name}"}

        try:
            import docker

            client = docker.from_env()
            container = client.containers.get(name)
            container.restart(timeout=10)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        return {"ok": True, "message": f"Container restarted: {name}"}

    def start_container(self, name: str) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "actions are disabled"}
        name = name.strip()
        if not name:
            return {"ok": False, "error": "container name is required"}
        if name in self.blocked_containers:
            return {"ok": False, "error": f"container start is blocked: {name}"}

        try:
            import docker

            client = docker.from_env()
            container = client.containers.get(name)
            container.start()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        return {"ok": True, "message": f"Container started: {name}"}

    def restart_network_interface(self, interface: str) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "actions are disabled"}
        interface = interface.strip()
        if not interface:
            return {"ok": False, "error": "interface name is required"}
        if platform.system().lower() != "linux":
            return {"ok": False, "error": "network interface restart is only supported on Linux"}

        try:
            subprocess.run(["ip", "link", "set", "dev", interface, "down"], check=True, timeout=10, stderr=subprocess.PIPE, text=True)
            time.sleep(2)
            subprocess.run(["ip", "link", "set", "dev", interface, "up"], check=True, timeout=10, stderr=subprocess.PIPE, text=True)
            if shutil.which("dhclient"):
                subprocess.run(["dhclient", "-1", interface], check=False, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            elif shutil.which("networkctl"):
                subprocess.run(["networkctl", "renew", interface], check=False, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as exc:
            return {"ok": False, "error": (exc.stderr or str(exc)).strip()}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)}

        return {"ok": True, "message": f"Network interface restarted: {interface}"}

    def add_site(self, site: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "actions are disabled"}
        if not isinstance(site, dict):
            return {"ok": False, "error": "site must be a JSON object"}

        try:
            normalized = normalize_site(site)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        name = normalized["name"]
        runtime_sites = list(self.state.get("sites.custom", []))
        runtime_sites = [existing for existing in runtime_sites if str(existing.get("name", "")).lower() != name.lower()]
        runtime_sites.append(normalized)
        self.state.set("sites.custom", runtime_sites)
        return {"ok": True, "message": f"Site monitor saved: {name}"}

    def remove_site(self, name: str) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "actions are disabled"}
        name = name.strip()
        if not name:
            return {"ok": False, "error": "site name is required"}

        runtime_sites = list(self.state.get("sites.custom", []))
        remaining = [site for site in runtime_sites if str(site.get("name", "")).lower() != name.lower()]
        if len(remaining) == len(runtime_sites):
            return {"ok": False, "error": f"runtime site not found: {name}"}
        self.state.set("sites.custom", remaining)
        return {"ok": True, "message": f"Site monitor removed: {name}"}

    def silence_alerts(self, minutes: Any = None) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "actions are disabled"}
        try:
            duration = float(minutes) if minutes not in (None, "") else None
        except (TypeError, ValueError):
            return {"ok": False, "error": "minutes must be a number"}
        if duration is not None and duration <= 0:
            return {"ok": False, "error": "minutes must be greater than 0"}
        until = set_silence(self.state, duration)
        message = f"Alerts silenced for {duration:g} minutes" if until else "Alerts silenced until resumed"
        return {"ok": True, "message": message, "silenced_until": until}

    def resume_alerts(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "actions are disabled"}
        clear_silence(self.state)
        return {"ok": True, "message": "Alerts resumed"}

    def clear_events(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "actions are disabled"}
        self.history.clear()
        return {"ok": True, "message": "Recent events cleared"}
