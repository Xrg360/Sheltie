import logging
import hashlib
import json
import threading
import time
from datetime import datetime
from typing import Any, Callable

import docker
import requests

from monitors import __version__
from monitors.alerts import parse_duration, silence_active
from monitors.autofix import USER_STOPPED_KEY
from monitors.internet import ping_stats
from monitors.sites import configured_sites, probe_site
from monitors.telegram import redact


HELP_TEXT = """Sheltie commands:

Overview
/status - Current monitor state
/alerts - Active alerts and how long they have been firing
/events [n] - Last n events (default 10)
/health - CPU, RAM, disk and temperature
/uptime - Host and Sheltie uptime, load and swap
/disk - Usage for each monitored disk
/network - Interfaces and internet state
/ip - LAN, Tailscale and public IP addresses
/ping <host> - Ping a host 3 times
/version - Sheltie version

Containers
/docker - All containers
/stats [container] - CPU and memory (top 5, or one container)
/logs <container> [lines] - Last log lines (default 30)
/restart <container> - Restart a container
/start <container> - Start a stopped container
/stop <container> - Stop a container (auto-heal leaves it stopped)

Websites
/sites - Website monitors
/checksite <name> - Check one website right now
/addsite <name> <url> - Add a website monitor
/removesite <name> - Remove a runtime website monitor

Alerts and host
/silence [30m|2h|1d] - Pause alerts, optionally for a while
/resume - Resume alerts
/clearcache - Clear Linux RAM caches
/help - Show this help"""


# Commands that change something. If they were queued while Sheltie was offline,
# running them late could restart a container hours after it was wanted.
# /start on its own is Telegram's "open the bot" command; only /start <container> acts.
DESTRUCTIVE_COMMANDS = {"/restart", "/stop", "/start", "/clearcache", "/addsite", "/removesite", "/silence", "/resume"}

# Telegram rejects messages longer than 4096 characters.
MAX_MESSAGE_CHARS = 3900
DEFAULT_EVENTS = 10
MAX_EVENTS = 30
DEFAULT_LOG_LINES = 30
MAX_LOG_LINES = 100


def usage_bar(value: float, width: int = 10) -> str:
    filled = max(0, min(width, round(value / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def usage_label(value: float) -> str:
    if value >= 90:
        return "critical"
    if value >= 75:
        return "high"
    if value >= 50:
        return "busy"
    return "normal"


def temp_label(value: float | None) -> str:
    if value is None:
        return "unavailable"
    if value >= 85:
        return "very hot"
    if value >= 75:
        return "hot"
    if value >= 60:
        return "warm"
    return "normal"


def is_destructive(command: str, args: list[str]) -> bool:
    if command == "/start":
        return bool(args)
    return command in DESTRUCTIVE_COMMANDS


def clamp_count(value: str | None, default: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        return max(1, min(maximum, int(value)))
    except ValueError:
        return default


def human_bytes(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.0f}{unit}" if unit in ("B", "KB") else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


def human_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m" if minutes else f"{seconds}s"


def tail_text(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    """Keep the end of a long text (the newest log lines) within a Telegram message."""
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1):]


def state_icon(value: Any) -> str:
    if value is True:
        return "✅"
    if value is False:
        return "❌"
    return "❔"


def public_ip() -> str | None:
    """The address the internet sees, from Cloudflare's trace endpoint."""
    try:
        response = requests.get("https://1.1.1.1/cdn-cgi/trace", timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        return None
    for line in response.text.splitlines():
        if line.startswith("ip="):
            return line[3:].strip()
    return None


class TelegramCommandMonitor:
    def __init__(self, config: dict[str, Any], state: Any, notifier: Any, status_service: Any, action_service: Any) -> None:
        self.config = config
        self.state = state
        self.notifier = notifier
        self.status_service = status_service
        self.action_service = action_service
        telegram_config = config.get("telegram", {}) or {}
        self.command_max_age = parse_duration(telegram_config.get("command_max_age"), 300)
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()

    def start(self) -> None:
        if not self.notifier.enabled:
            return
        self._reset_offset_if_bot_changed()
        self._prepare_polling()
        self.thread = threading.Thread(target=self._run, name="telegram-commands", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _run(self) -> None:
        logging.info("Telegram command listener started")
        while not self.stop_event.is_set():
            try:
                self._poll_once()
            except Exception as exc:
                logging.error("Telegram command listener error: %s", redact(exc, self.notifier.bot_token))
                self.stop_event.wait(5)

    def _prepare_polling(self) -> None:
        bot_url = f"https://api.telegram.org/bot{self.notifier.bot_token}/getMe"
        try:
            bot_response = requests.get(bot_url, timeout=10)
            bot_response.raise_for_status()
            bot_info = bot_response.json().get("result", {})
            logging.info("Telegram command listener connected as @%s", bot_info.get("username", "unknown"))
        except requests.RequestException as exc:
            response_text = getattr(getattr(exc, "response", None), "text", "")
            logging.warning(
                "Could not verify Telegram bot identity: %s %s",
                redact(exc, self.notifier.bot_token),
                redact(response_text, self.notifier.bot_token),
            )

        url = f"https://api.telegram.org/bot{self.notifier.bot_token}/deleteWebhook"
        try:
            response = requests.post(url, json={"drop_pending_updates": False}, timeout=10)
            response.raise_for_status()
            logging.info("Telegram webhook cleared for command polling")
        except requests.RequestException as exc:
            response_text = getattr(getattr(exc, "response", None), "text", "")
            logging.warning(
                "Could not clear Telegram webhook before polling: %s %s",
                redact(exc, self.notifier.bot_token),
                redact(response_text, self.notifier.bot_token),
            )

    def _reset_offset_if_bot_changed(self) -> None:
        fingerprint = hashlib.sha256(str(self.notifier.bot_token).encode("utf-8")).hexdigest()
        key = "telegram.bot_fingerprint"
        if self.state.get(key) != fingerprint:
            self.state.set("telegram.update_offset", None)
            self.state.set(key, fingerprint)
            logging.info("Telegram bot token changed or first seen; command polling offset reset")

    def _poll_once(self) -> None:
        offset = self.state.get("telegram.update_offset")
        params: dict[str, Any] = {"timeout": 25, "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            params["offset"] = offset

        url = f"https://api.telegram.org/bot{self.notifier.bot_token}/getUpdates"
        response = requests.get(url, params=params, timeout=35)
        if response.status_code == 409:
            logging.warning("Telegram polling conflict detected; clearing webhook and retrying")
            self._prepare_polling()
            self.stop_event.wait(2)
            return
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            response_text = getattr(exc.response, "text", "")
            logging.error(
                "Telegram getUpdates failed: %s %s",
                redact(exc, self.notifier.bot_token),
                redact(response_text, self.notifier.bot_token),
            )
            raise

        payload = response.json()
        if not payload.get("ok"):
            logging.warning("Telegram getUpdates returned non-ok response: %s", payload)
            self.stop_event.wait(5)
            return

        for update in payload.get("result", []):
            update_id = update.get("update_id")
            if update_id is not None:
                self.state.set("telegram.update_offset", update_id + 1)
            self._handle_update(update)

    def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id"))
        if chat_id != str(self.notifier.chat_id):
            logging.info("Ignoring Telegram command from unauthorized chat %s; configured chat is %s", chat_id, self.notifier.chat_id)
            return

        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return

        parts = text.split()
        command = parts[0].split("@")[0].lower()
        sent_at = float(message.get("date") or time.time())
        age = time.time() - sent_at
        args = parts[1:]
        if age > self.command_max_age:
            logging.info("Ignoring stale Telegram command %s sent %.0fs ago", command, age)
            if is_destructive(command, args):
                sent_label = datetime.fromtimestamp(sent_at).strftime("%Y-%m-%d %H:%M")
                self.notifier.send(
                    f"⏳ Ignored {command} sent at {sent_label} ({age / 60:.0f} min ago) while Sheltie was offline. "
                    "Send it again if it is still needed.",
                    force=True,
                )
            return

        logging.info("Handling Telegram command %s from chat %s", command, chat_id)
        handlers: dict[str, Callable[[list[str]], str]] = {
            "/start": self._start,
            "/help": lambda _args: self._help(),
            "/status": lambda _args: self._status(),
            "/health": lambda _args: self._health(),
            "/network": lambda _args: self._network(),
            "/docker": lambda _args: self._docker(),
            "/sites": lambda _args: self._sites(),
            "/clearcache": lambda _args: self._clear_cache(),
            "/restart": lambda args: self._restart(args[0] if args else ""),
            "/addsite": lambda _args: self._add_site(parts),
            "/removesite": lambda args: self._remove_site(" ".join(args)),
            "/silence": self._silence,
            "/resume": lambda _args: self._resume(),
            "/alerts": lambda _args: self._alerts(),
            "/events": self._events,
            "/logs": self._logs,
            "/stats": self._stats,
            "/stop": self._stop,
            "/uptime": lambda _args: self._uptime(),
            "/disk": lambda _args: self._disk(),
            "/ip": lambda _args: self._ip(),
            "/ping": self._ping,
            "/checksite": self._checksite,
            "/version": lambda _args: self._version(),
        }

        handler = handlers.get(command)
        if not handler:
            self.notifier.send("Unknown command. Use /help.", force=True)
            return
        try:
            reply = handler(args)
        except docker.errors.NotFound:
            reply = f"⚠️ No container called {args[0] if args else '?'}. Use /docker to list them."
        except Exception as exc:
            logging.exception("Telegram command %s failed", command)
            reply = f"⚠️ {command} failed: {redact(exc, self.notifier.bot_token)}"
        self.notifier.send(reply, force=True)

    def _help(self) -> str:
        return HELP_TEXT

    def _status(self) -> str:
        status = self.status_service.status()

        return "\n".join(
            [
                "🦫 Sheltie status",
                "",
                f"🔔 Alerts: {'silenced' if status['alerts_silenced'] else 'active'}",
                f"🚨 Active alerts: {len(status['active_alerts'])}",
                f"{state_icon(status['internet_up'])} Internet: {self._state_label(status['internet_up'])}",
                f"{state_icon(status['ethernet_up'])} Ethernet: {self._state_label(status['ethernet_up'])}",
                f"{state_icon(status['wifi_up'])} Wi-Fi: {self._state_label(status['wifi_up'])}",
                f"🧭 Default route: {status['default_route_label']}",
            ]
        )

    def _health(self) -> str:
        health = self.status_service.health()
        temp = health["cpu_temperature"]
        temp_text = f"{temp:.0f}degC ({temp_label(temp)})" if temp is not None else "unavailable"

        return "\n".join(
            [
                "📊 System health",
                "",
                f"🧠 CPU  {usage_bar(health['cpu_percent'])} {health['cpu_percent']:.0f}% ({usage_label(health['cpu_percent'])})",
                f"💾 RAM  {usage_bar(health['ram_percent'])} {health['ram_percent']:.0f}% ({usage_label(health['ram_percent'])})",
                f"🗄 Disk {usage_bar(health['disk_percent'])} {health['disk_percent']:.0f}% ({usage_label(health['disk_percent'])})",
                f"🌡 CPU temp: {temp_text}",
            ]
        )

    def _network(self) -> str:
        network = self.status_service.network()
        lines = ["🌐 Network", ""]

        for label, status in network["interfaces"].items():
            lines.append(
                f"{state_icon(status['up'])} {label.title()} {status['name']}: {'up' if status['up'] else 'down'} "
                f"(state={status['operstate']}, carrier={status['carrier']}, ip={status['has_ip']})"
            )

        lines.append(f"🧭 Default route: {network['default_route_label']}")
        lines.append(f"{state_icon(network['internet_up'])} Internet: {self._state_label(network['internet_up'])}")
        return "\n".join(lines)

    def _docker(self) -> str:
        docker_status = self.status_service.docker()
        if not docker_status["available"]:
            return f"🐳 Docker unavailable: {docker_status['error']}"

        containers = docker_status["containers"]
        if not containers:
            return "🐳 Docker\n\nNo containers found."

        lines = ["🐳 Docker", ""]
        for container in containers[:20]:
            icon = "✅" if container["status"] == "running" else "⚠️"
            lines.append(f"{icon} {container['name']}: {container['status']}")
        if len(containers) > 20:
            lines.append(f"...and {len(containers) - 20} more")
        return "\n".join(lines)

    def _sites(self) -> str:
        sites = self.status_service.sites()
        if not sites["sites"]:
            return "🌍 Sites\n\nNo website monitors configured."

        lines = [f"🌍 Sites ({sites['up']}/{sites['total']} up)", ""]
        for site in sites["sites"][:20]:
            icon = state_icon(site.get("up"))
            latency = site.get("latency_ms")
            status_code = site.get("status_code") or "none"
            lines.append(f"{icon} {site['name']} - {status_code} - {latency if latency is not None else 'unknown'}ms")
        if len(sites["sites"]) > 20:
            lines.append(f"...and {len(sites['sites']) - 20} more")
        return "\n".join(lines)

    def _add_site(self, parts: list[str]) -> str:
        if len(parts) < 3:
            return "Usage: /addsite name https://example.com"
        result = self.action_service.add_site({"name": parts[1], "url": parts[2]})
        if result["ok"]:
            return f"🌍 Site monitor added\n\n{result['message']}"
        return f"⚠️ Site monitor add failed\n\n{result['error']}"

    def _remove_site(self, name: str) -> str:
        result = self.action_service.remove_site(name)
        if result["ok"]:
            return f"🗑 Site monitor removed\n\n{result['message']}"
        return f"⚠️ Site monitor remove failed\n\n{result['error']}"

    def _clear_cache(self) -> str:
        result = self.action_service.clear_ram_cache()
        if result["ok"]:
            return f"🧹 RAM cache cleared\n\n{result['message']}"
        return f"⚠️ RAM cache clear failed\n\n{result['error']}"

    def _restart(self, container: str) -> str:
        result = self.action_service.restart_container(container)
        if result["ok"]:
            return f"🔁 Docker restart requested\n\n{result['message']}"
        return f"⚠️ Docker restart failed\n\n{result['error']}"

    def _silence(self, args: list[str]) -> str:
        minutes = None
        if args:
            try:
                seconds = parse_duration(args[0])
            except ValueError:
                return "Usage: /silence [30m|2h|1d]"
            if seconds <= 0:
                return "Usage: /silence [30m|2h|1d]"
            minutes = seconds / 60
        result = self.action_service.silence_alerts(minutes)
        if not result["ok"]:
            return f"⚠️ Silence failed\n\n{result['error']}"
        if minutes:
            return f"🔕 Alerts silenced for {human_duration(minutes * 60)}. Use /resume to enable them sooner."
        return "🔕 Alerts silenced. Use /resume to enable alerts again."

    def _resume(self) -> str:
        result = self.action_service.resume_alerts()
        if not result["ok"]:
            return f"⚠️ Resume failed\n\n{result['error']}"
        return "🔔 Alerts resumed."

    def _start(self, args: list[str]) -> str:
        if not args:
            return self._help()
        result = self.action_service.start_container(args[0])
        if result["ok"]:
            # A manual start means the operator wants it running again.
            stopped = set(self.state.get(USER_STOPPED_KEY, []))
            stopped.discard(args[0])
            self.state.set(USER_STOPPED_KEY, sorted(stopped))
            return f"▶️ Container started\n\n{result['message']}"
        return f"⚠️ Container start failed\n\n{result['error']}"

    def _stop(self, args: list[str]) -> str:
        if not args:
            return "Usage: /stop container_name"
        result = self.action_service.stop_container(args[0])
        if result["ok"]:
            return f"⏹ Container stopped\n\n{result['message']}"
        return f"⚠️ Container stop failed\n\n{result['error']}"

    def _alerts(self) -> str:
        active = self.status_service.active_alerts()
        if not active:
            return "✅ No active alerts."
        now = time.time()
        lines = [f"🚨 Active alerts ({len(active)})", ""]
        for alert_id in active[:30]:
            since = self.state.get(f"alerts.{alert_id}.active_since")
            age = f" - firing for {human_duration(now - float(since))}" if since else ""
            lines.append(f"• {alert_id}{age}")
        if silence_active(self.state):
            lines.extend(["", "🔕 Notifications are silenced. Use /resume."])
        return "\n".join(lines)

    def _events(self, args: list[str]) -> str:
        count = clamp_count(args[0] if args else None, DEFAULT_EVENTS, MAX_EVENTS)
        events = self.status_service.history.recent(count)
        if not events:
            return "🗒 No events recorded yet."
        icons = {"active": "🚨", "recovered": "✅", "changed": "🔄", "event": "ℹ️"}
        lines = [f"🗒 Last {len(events)} events", ""]
        for event in events:
            stamp = str(event.get("ts", ""))[:16].replace("T", " ")
            lines.append(f"{icons.get(event.get('status'), '•')} {stamp} {event.get('title')}")
        return tail_text("\n".join(lines))

    def _logs(self, args: list[str]) -> str:
        if not args:
            return "Usage: /logs container_name [lines]"
        name = args[0]
        lines = clamp_count(args[1] if len(args) > 1 else None, DEFAULT_LOG_LINES, MAX_LOG_LINES)
        output = redact(self.status_service.container_logs(name, lines), self.notifier.bot_token).strip()
        if not output:
            return f"📜 {name}: no log output."
        return tail_text(f"📜 {name} (last {lines} lines)\n\n{output}")

    def _stats(self, args: list[str]) -> str:
        usage = self.status_service.container_stats(args[0] if args else None)
        if not usage:
            return "🐳 No running containers."
        rows = [row for row in usage if "error" not in row]
        rows.sort(key=lambda row: (row["cpu_percent"], row["memory_used"]), reverse=True)
        title = f"📈 {args[0]}" if args else f"📈 Top {min(5, len(rows))} containers by CPU"
        lines = [title, ""]
        for row in rows[: 1 if args else 5]:
            memory = human_bytes(row["memory_used"])
            if row.get("memory_percent") is not None:
                memory += f" ({row['memory_percent']:.0f}%)"
            lines.append(f"• {row['name']}: CPU {row['cpu_percent']:.1f}% · RAM {memory}")
        for row in usage:
            if "error" in row:
                lines.append(f"• {row['name']}: unavailable ({row['error']})")
        return "\n".join(lines)

    def _uptime(self) -> str:
        host = self.status_service.host()
        load = host.get("load_average")
        load_text = " / ".join(f"{value:.2f}" for value in load) if load else "unavailable"
        return "\n".join(
            [
                "⏱ Uptime",
                "",
                f"🖥 Host: {human_duration(host['uptime_seconds'])}",
                f"🐕 Sheltie: {human_duration(host['sheltie_uptime_seconds'])}",
                f"⚖️ Load (1/5/15m): {load_text} on {host.get('cpu_count') or '?'} CPUs",
                f"🔁 Swap: {human_bytes(host['swap_used'])} of {human_bytes(host['swap_total'])} ({host['swap_percent']:.0f}%)",
            ]
        )

    def _disk(self) -> str:
        lines = ["🗄 Disks", ""]
        for disk in self.status_service.disks():
            if "error" in disk:
                lines.append(f"❔ {disk['path']}: {disk['error']}")
                continue
            lines.append(
                f"{usage_bar(disk['percent'])} {disk['percent']:.0f}% {disk['path']} "
                f"({human_bytes(disk['free'])} free of {human_bytes(disk['total'])})"
            )
        return "\n".join(lines)

    def _ip(self) -> str:
        lines = ["🧭 Addresses", ""]
        for interface, ips in self.status_service.addresses().items():
            lines.append(f"• {interface}: {', '.join(ips)}")
        lines.append(f"🌍 Public: {public_ip() or 'unavailable'}")
        return "\n".join(lines)

    def _ping(self, args: list[str]) -> str:
        if not args:
            return "Usage: /ping host"
        try:
            stats = ping_stats(args[0])
        except ValueError as exc:
            return f"⚠️ {exc}"
        if stats.get("avg_ms") is None:
            return f"❌ {stats['host']}: no reply ({stats.get('error', 'unreachable')})"
        loss = stats.get("loss_percent")
        loss_text = f", loss {loss:.0f}%" if loss is not None else ""
        return (
            f"{state_icon(stats['ok'])} {stats['host']}: avg {stats['avg_ms']:.1f}ms "
            f"(min {stats['min_ms']:.1f} / max {stats['max_ms']:.1f}){loss_text}"
        )

    def _checksite(self, args: list[str]) -> str:
        query = " ".join(args).strip().strip("\"'")
        if not query:
            return "Usage: /checksite name"
        sites = configured_sites(self.config, self.state)
        match = next((site for site in sites if str(site.get("name", "")).lower() == query.lower()), None)
        if match is None:
            names = ", ".join(str(site.get("name")) for site in sites) or "none"
            return f"⚠️ No site called {query}. Monitored sites: {names}"
        result = probe_site(match)
        if result is None:
            return f"⚠️ {query} has no URL configured."
        lines = [
            f"{state_icon(result['up'])} {result['name']} is {'up' if result['up'] else 'DOWN'}",
            "",
            f"URL: {result['url']}",
            f"Status: {result['status_code'] or 'none'} (expected {', '.join(str(code) for code in result['expected_status'])})",
            f"Latency: {result['latency_ms']}ms",
        ]
        if result["error"]:
            lines.append(f"Error: {result['error']}")
        return "\n".join(lines)

    def _version(self) -> str:
        status = self.status_service.status()
        return f"🐕 Sheltie {__version__}\nRunning since {str(status.get('started_at', ''))[:16].replace('T', ' ')} UTC"

    @staticmethod
    def _state_label(value: Any) -> str:
        if value is True:
            return "up"
        if value is False:
            return "down"
        return "unknown"
