import platform
import re
import subprocess
from typing import Any


# Hostnames and IPv4/IPv6 literals only. The first character can never be "-",
# so a value can't be read as a ping option.
PING_TARGET_PATTERN = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,62})(?:\.[A-Za-z0-9-]{1,63})*\.?|[0-9A-Fa-f:]*:[0-9A-Fa-f:.]+)$")


def ping(host: str, timeout: int) -> bool:
    if platform.system().lower() == "windows":
        command = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
    else:
        command = ["ping", "-c", "1", "-W", str(timeout), host]

    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout + 2)
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def ping_stats(host: str, count: int = 3, timeout: int = 2) -> dict[str, Any]:
    """Ping `host` a few times and return packet loss and round-trip times (Linux ping output)."""
    if len(host) > 253 or not PING_TARGET_PATTERN.match(host):
        raise ValueError("not a valid hostname or IP address")

    command = ["ping", "-c", str(count), "-W", str(timeout), host]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=count * (timeout + 1) + 5)
    except (subprocess.SubprocessError, OSError) as exc:
        return {"host": host, "ok": False, "error": str(exc)}

    output = result.stdout
    loss = re.search(r"([\d.]+)% packet loss", output)
    rtt = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)", output)
    stats: dict[str, Any] = {
        "host": host,
        "ok": result.returncode == 0,
        "sent": count,
        "loss_percent": float(loss.group(1)) if loss else None,
    }
    if rtt:
        stats.update(min_ms=float(rtt.group(1)), avg_ms=float(rtt.group(2)), max_ms=float(rtt.group(3)))
    if result.returncode != 0 and not rtt:
        stats["error"] = (result.stderr or output).strip().splitlines()[-1] if (result.stderr or output).strip() else "no reply"
    return stats


def check_internet(config: dict[str, Any], state: Any, notifier: Any) -> None:
    internet_config = config.get("internet", {}) or {}
    hosts = internet_config.get("hosts") or ["1.1.1.1", "8.8.8.8"]
    timeout = int(internet_config.get("timeout", 2))

    reachable = any(ping(host, timeout) for host in hosts)
    state.set("internet.up", reachable)
    notifier.condition(
        alert_id="internet.down",
        source="internet",
        active=not reachable,
        severity=internet_config.get("severity", "critical"),
        title="Internet lost",
        alert_body=f"All probes failed: {', '.join(hosts)}",
        recovery_body=f"At least one probe is reachable: {', '.join(hosts)}",
        duration=internet_config.get("duration", 0),
        cooldown=internet_config.get("cooldown"),
    )
