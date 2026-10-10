import logging
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import docker
import requests

from monitors import __version__
from monitors.alerts import parse_duration, silence_active
from monitors.autofix import USER_STOPPED_KEY
from monitors.internet import ping_stats
from monitors.sites import configured_sites, probe_site
from monitors.telegram import Buttons, esc, redact


# (command, arguments, description, section). The single source for /help and the
# Telegram command menu, so the two never drift apart.
COMMANDS: list[tuple[str, str, str, str]] = [
    ("/status", "", "Everything at a glance", "Overview"),
    ("/menu", "", "Control panel with buttons", "Overview"),
    ("/alerts", "", "Active alerts and how long they have been firing", "Overview"),
    ("/events", "[n]", "Last n events (default 10)", "Overview"),
    ("/health", "", "CPU, memory, disk and temperature", "Overview"),
    ("/uptime", "", "Host and Sheltie uptime, load and swap", "Overview"),
    ("/disk", "", "Usage for each monitored disk", "Overview"),
    ("/version", "", "Sheltie version", "Overview"),
    ("/power", "", "AC adapter, battery and power-on-with-AC", "Power"),
    ("/autoon", "[on|off]", "Show or change power on when AC is connected", "Power"),
    ("/network", "", "Interfaces and internet state", "Network"),
    ("/ip", "", "LAN, Tailscale and public IP addresses", "Network"),
    ("/ping", "<host>", "Ping a host 3 times", "Network"),
    ("/docker", "", "All containers, with start buttons for stopped ones", "Containers"),
    ("/stats", "[container]", "CPU and memory (top 5, or one container)", "Containers"),
    ("/logs", "<container> [lines]", "Last log lines (default 30)", "Containers"),
    ("/restart", "<container>", "Restart a container", "Containers"),
    ("/start", "<container>", "Start a stopped container", "Containers"),
    ("/stop", "<container>", "Stop a container (auto-heal leaves it stopped)", "Containers"),
    ("/heal", "", "What auto-heal is watching", "Containers"),
    ("/sites", "", "Website monitors", "Websites"),
    ("/checksite", "<name>", "Check one website right now", "Websites"),
    ("/addsite", "<name> <url>", "Add a website monitor", "Websites"),
    ("/removesite", "<name>", "Remove a runtime website monitor", "Websites"),
    ("/silence", "[30m|2h|1d]", "Silence alerts, optionally for a while", "Alerts and host"),
    ("/resume", "", "Resume alerts", "Alerts and host"),
    ("/clearcache", "", "Clear Linux RAM caches", "Alerts and host"),
    ("/help", "", "Show this help", "Alerts and host"),
]

ALIASES = {"/containers": "/docker", "/battery": "/power", "/acpower": "/autoon", "/unsilence": "/resume", "/commands": "/help"}


def help_text() -> str:
    lines = ["🐕 <b>Sheltie commands</b>", "<i>Tap a command, or use /menu for buttons.</i>"]
    section = None
    for command, args, description, group in COMMANDS:
        if group != section:
            section = group
            lines += ["", f"<b>{esc(group)}</b>"]
        usage = f"{command} {esc(args)}".strip()
        lines.append(f"{usage} - {esc(description)}")
    return "\n".join(lines)


HELP_TEXT = help_text()


# Commands that change something. If they were queued while Sheltie was offline,
# running them late could restart a container hours after it was wanted.
# /start on its own is Telegram's "open the bot" command; only /start <container> acts.
# /autoon on its own only shows the setting.
DESTRUCTIVE_COMMANDS = {"/restart", "/stop", "/start", "/clearcache", "/addsite", "/removesite", "/silence", "/resume", "/autoon"}

# Commands that ask "are you sure?" when they come from a button. A typed command is
# already deliberate; a tap on an old message may not be.
CONFIRM_COMMANDS = {"/restart", "/stop", "/clearcache", "/removesite", "/autoon"}

# Telegram rejects messages longer than 4096 characters.
MAX_MESSAGE_CHARS = 3900
DEFAULT_EVENTS = 10
MAX_EVENTS = 30
DEFAULT_LOG_LINES = 30
MAX_LOG_LINES = 100
MAX_LIST_ITEMS = 20
MAX_PICKER_BUTTONS = 12


@dataclass
class Reply:
    """A formatted (HTML) reply with optional inline buttons."""

    text: str
    buttons: Buttons = field(default_factory=list)


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


def usage_icon(value: float, warn: float = 75, bad: float = 90) -> str:
    if value >= bad:
        return "🔴"
    if value >= warn:
        return "🟠"
    return "🟢"


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
    if command in ("/start", "/autoon"):
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


def state_label(value: Any) -> str:
    if value is True:
        return "up"
    if value is False:
        return "down"
    return "unknown"


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


def confirm_data(command_line: str, now: float | None = None) -> str:
    """Callback data for the "yes" button of a confirmation, stamped so it expires."""
    stamp = int(now if now is not None else time.time())
    return f"y:{stamp:x}:{command_line}"


def confirm_prompt(command: str, args: list[str]) -> tuple[str, str]:
    """(question, consequence) shown before a button runs a disruptive command."""
    target = esc(" ".join(args))
    if command == "/restart":
        return f"Restart {target}?", "The container stops and starts again. Anything it serves is briefly unavailable."
    if command == "/stop":
        return f"Stop {target}?", "Auto-heal will leave it stopped until you start it again."
    if command == "/clearcache":
        return "Clear the Linux page cache?", "It is safe, but disks are busier for a while as the cache refills."
    if command == "/removesite":
        return f"Remove the {target} monitor?", "Sheltie stops checking this site."
    if command == "/autoon":
        if args and args[0].lower() == "off":
            return "Turn off power on with AC?", "After a power cut, this machine will stay off until someone presses the power button."
        return "Turn on power on with AC?", "This changes a BIOS setting. After a power cut, the machine will start by itself when power returns."
    return f"Run {esc(command)}?", ""


ACTION_LABELS = {"/restart": "Restart", "/stop": "Stop", "/clearcache": "Clear cache", "/removesite": "Remove"}


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
        self.handlers: dict[str, Callable[[list[str]], str | Reply]] = {
            "/start": self._start,
            "/help": lambda _args: self._help(),
            "/menu": lambda _args: self._menu(),
            "/status": lambda _args: self._status(),
            "/health": lambda _args: self._health(),
            "/network": lambda _args: self._network(),
            "/docker": lambda _args: self._docker(),
            "/sites": lambda _args: self._sites(),
            "/clearcache": lambda _args: self._clear_cache(),
            "/restart": self._restart,
            "/addsite": self._add_site,
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
            "/power": lambda _args: self._power(),
            "/autoon": self._autoon,
            "/heal": lambda _args: self._heal(),
        }

    def start(self) -> None:
        if not self.notifier.enabled:
            return
        self._reset_offset_if_bot_changed()
        self._prepare_polling()
        self.notifier.set_commands([(command, description) for command, _args, description, _group in COMMANDS])
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
        params: dict[str, Any] = {"timeout": 25, "allowed_updates": json.dumps(["message", "callback_query"])}
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

    def _authorized(self, chat: dict[str, Any]) -> bool:
        chat_id = str(chat.get("id"))
        if chat_id != str(self.notifier.chat_id):
            logging.info("Ignoring Telegram update from unauthorized chat %s; configured chat is %s", chat_id, self.notifier.chat_id)
            return False
        return True

    def _handle_update(self, update: dict[str, Any]) -> None:
        if update.get("callback_query"):
            self._handle_callback(update["callback_query"])
            return

        message = update.get("message") or {}
        if not self._authorized(message.get("chat") or {}):
            return

        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return

        parts = text.split()
        command = ALIASES.get(parts[0].split("@")[0].lower(), parts[0].split("@")[0].lower())
        sent_at = float(message.get("date") or time.time())
        age = time.time() - sent_at
        args = parts[1:]
        if age > self.command_max_age:
            logging.info("Ignoring stale Telegram command %s sent %.0fs ago", command, age)
            if is_destructive(command, args):
                sent_label = datetime.fromtimestamp(sent_at).strftime("%Y-%m-%d %H:%M")
                self.notifier.send(
                    f"⏳ Ignored {esc(command)} sent at {sent_label} ({age / 60:.0f} min ago) while Sheltie was offline. "
                    "Send it again if it is still needed.",
                    force=True,
                    html=True,
                )
            return

        logging.info("Handling Telegram command %s", command)
        self._reply(self._run_command(command, args))

    def _handle_callback(self, query: dict[str, Any]) -> None:
        message = query.get("message") or {}
        if not self._authorized(message.get("chat") or {}):
            return
        data = str(query.get("data") or "")
        callback_id = query.get("id")
        message_id = message.get("message_id")

        if data == "n":
            self.notifier.answer_callback(callback_id, "Cancelled")
            self.notifier.edit(message_id, "Cancelled. Nothing was changed.")
            return

        if data.startswith("y:"):
            _prefix, stamp, command_line = (data.split(":", 2) + ["", ""])[:3]
            try:
                age = time.time() - int(stamp, 16)
            except ValueError:
                age = float("inf")
            if age > self.command_max_age:
                self.notifier.answer_callback(callback_id, "This button has expired")
                self.notifier.edit(message_id, "⏳ This confirmation expired. Run the command again if it is still needed.")
                return
            parts = command_line.split()
            if not parts:
                self.notifier.answer_callback(callback_id)
                return
            self.notifier.answer_callback(callback_id, "Working on it…")
            logging.info("Handling confirmed Telegram button %s", parts[0])
            reply = self._run_command(parts[0], parts[1:])
            self.notifier.edit(message_id, reply.text, buttons=reply.buttons)
            return

        if data.startswith("c:"):
            parts = data[2:].split()
            if not parts:
                self.notifier.answer_callback(callback_id)
                return
            command, args = parts[0], parts[1:]
            self.notifier.answer_callback(callback_id)
            logging.info("Handling Telegram button %s", command)
            # Commands that need a target show a picker first, so only ask once there is one.
            if (command in CONFIRM_COMMANDS and args) or command == "/clearcache":
                question, consequence = confirm_prompt(command, args)
                text = f"⚠️ <b>{question}</b>" + (f"\n{consequence}" if consequence else "")
                label = ACTION_LABELS.get(command, "Confirm")
                if command == "/autoon":
                    label = "Turn off" if args[0].lower() == "off" else "Turn on"
                buttons = [[(f"✅ {label}", confirm_data(" ".join(parts))), ("Cancel", "n")]]
                self._reply(Reply(text, buttons))
                return
            self._reply(self._run_command(command, args))
            return

        self.notifier.answer_callback(callback_id)

    def _run_command(self, command: str, args: list[str]) -> Reply:
        command = ALIASES.get(command, command)
        handler = self.handlers.get(command)
        if not handler:
            return Reply(f"I don't know {esc(command)}. Try /help, or /menu for buttons.")
        try:
            result = handler(args)
        except docker.errors.NotFound:
            result = f"⚠️ No container called {esc(args[0] if args else '?')}. Use /docker to list them."
        except Exception as exc:
            logging.exception("Telegram command %s failed", command)
            result = f"⚠️ {esc(command)} failed: {esc(redact(exc, self.notifier.bot_token))}"
        return result if isinstance(result, Reply) else Reply(result)

    def _reply(self, reply: Reply) -> None:
        self.notifier.send(reply.text, force=True, html=True, buttons=reply.buttons)

    # ---- helpers -----------------------------------------------------------------

    def _section(self, name: str) -> Any:
        """One part of /status. A failing part is left out instead of failing the whole reply."""
        try:
            return getattr(self.status_service, name)()
        except Exception:
            logging.debug("Telegram status section %s failed", name, exc_info=True)
            return None

    def _alert_titles(self) -> dict[str, str]:
        """Readable titles for alert ids, from the most recent matching event."""
        titles: dict[str, str] = {}
        try:
            events = self.status_service.history.recent(200)
        except Exception:
            events = []
        for event in events:
            alert_id = event.get("alert_id")
            if alert_id and alert_id not in titles and event.get("status") == "active":
                titles[alert_id] = str(event.get("title") or alert_id)
        return titles

    def _containers(self) -> list[dict[str, Any]]:
        docker_status = self._section("docker") or {}
        return list(docker_status.get("containers") or [])

    def _picker(self, command: str, question: str, include: Callable[[dict[str, Any]], bool]) -> Reply:
        """A container chooser for a command typed without a name."""
        names = [entry["name"] for entry in self._containers() if not entry.get("blocked") and include(entry)]
        if not names:
            return Reply(f"Usage: {esc(command)} container_name\n\nNo containers to choose from. Use /docker to list them.")
        buttons: Buttons = []
        for name in names[:MAX_PICKER_BUTTONS]:
            if not buttons or len(buttons[-1]) == 2:
                buttons.append([])
            buttons[-1].append((name, f"c:{command} {name}"))
        return Reply(f"<b>{esc(question)}</b>\nTap a container, or type {esc(command)} container_name.", buttons)

    def _silence_buttons(self) -> list[tuple[str, str]]:
        if silence_active(self.state):
            return [("🔔 Resume alerts", "c:/resume")]
        return [("🔕 Silence 1h", "c:/silence 1h"), ("🔕 4h", "c:/silence 4h")]

    # ---- overview ----------------------------------------------------------------

    def _help(self) -> Reply:
        return Reply(HELP_TEXT, [[("🎛 Open the menu", "c:/menu")]])

    def _menu(self) -> Reply:
        buttons: Buttons = [
            [("📋 Status", "c:/status"), ("🚨 Alerts", "c:/alerts")],
            [("📊 Health", "c:/health"), ("🔌 Power", "c:/power")],
            [("🐳 Containers", "c:/docker"), ("🌍 Sites", "c:/sites")],
            [("🌐 Network", "c:/network"), ("🗒 Events", "c:/events")],
            [("📈 Container stats", "c:/stats"), ("🩹 Auto-heal", "c:/heal")],
            self._silence_buttons(),
            [("🧹 Clear RAM cache", "c:/clearcache")],
        ]
        return Reply("🎛 <b>Sheltie control panel</b>\nWhat do you want to see or do?", buttons)

    def _status(self) -> Reply:
        status = self._section("status") or {}
        health = self._section("health")
        containers = self._containers()
        sites = self._section("sites")
        power = self._section("power")
        active = list(self._section("active_alerts") or [])

        if active:
            titles = self._alert_titles()
            headline = f"🚨 <b>{len(active)} problem{'s' if len(active) != 1 else ''} need{'s' if len(active) == 1 else ''} attention</b>"
            problem_lines = [f"• {esc(titles.get(alert_id, alert_id))}" for alert_id in active[:5]]
            if len(active) > 5:
                problem_lines.append(f"…and {len(active) - 5} more. Use /alerts.")
        else:
            headline = "✅ <b>All systems normal</b>"
            problem_lines = []

        lines = [headline]
        started = str(status.get("started_at") or "")[:16].replace("T", " ")
        lines.append(f"<i>Sheltie {esc(status.get('version') or __version__)}" + (f" · running since {esc(started)} UTC" if started else "") + "</i>")
        if problem_lines:
            lines += [""] + problem_lines

        lines += ["", "<b>Network</b>"]
        lines.append(f"{state_icon(status.get('internet_up'))} Internet {state_label(status.get('internet_up'))}")
        lines.append(
            f"{state_icon(status.get('ethernet_up'))} Ethernet {state_label(status.get('ethernet_up'))}  "
            f"{state_icon(status.get('wifi_up'))} Wi-Fi {state_label(status.get('wifi_up'))}"
        )
        lines.append(f"🧭 Route: {esc(status.get('default_route_label') or 'unknown')}")

        if health:
            temp = health.get("cpu_temperature")
            temp_text = f" · {temp:.0f}°C" if temp is not None else ""
            lines += [
                "",
                "<b>Host</b>",
                f"CPU {health['cpu_percent']:.0f}% · Memory {health['ram_percent']:.0f}% · Disk {health['disk_percent']:.0f}%{temp_text}",
            ]

        service_lines = []
        if containers:
            running = len([entry for entry in containers if entry.get("status") == "running"])
            service_lines.append(f"🐳 {running} of {len(containers)} containers running")
        if sites and sites.get("total"):
            service_lines.append(f"🌍 {sites['up']} of {sites['total']} sites up")
        if service_lines:
            lines += ["", "<b>Services</b>"] + service_lines

        buttons: Buttons = [
            [("🚨 Alerts", "c:/alerts"), ("📊 Health", "c:/health")],
            [("🐳 Containers", "c:/docker"), ("🌍 Sites", "c:/sites")],
        ]
        if power:
            lines += ["", "<b>Power</b>", self._supply_line(power)]
            recovery = power.get("ac_recovery") or {}
            if recovery.get("supported"):
                lines.append(self._recovery_line(recovery))
                if recovery.get("mode") == "off":
                    buttons.append([("⚡ Turn on power-on with AC", "c:/autoon on")])

        lines += ["", "🔕 Alerts silenced. Use /resume." if status.get("alerts_silenced") else "🔔 Alerts on"]
        buttons.append([("🔌 Power", "c:/power"), ("🔄 Refresh", "c:/status")])
        return Reply("\n".join(lines), buttons)

    def _health(self) -> Reply:
        health = self.status_service.health()
        temp = health["cpu_temperature"]
        temp_text = f"{temp:.0f}°C ({temp_label(temp)})" if temp is not None else "unavailable"
        busy = [
            name
            for name, value, limit in (("CPU", health["cpu_percent"], 75), ("Memory", health["ram_percent"], 75), ("Disk", health["disk_percent"], 90))
            if value >= limit
        ]
        headline = f"🟠 <b>{busy[0]} is running high</b>" if busy else "🟢 <b>Host is healthy</b>"

        def row(label: str, value: float, warn: float = 75, bad: float = 90) -> str:
            return f"{usage_icon(value, warn, bad)} <code>{label:<6} {usage_bar(value)} {value:>3.0f}%</code> {usage_label(value)}"

        lines = [
            headline,
            "",
            row("CPU", health["cpu_percent"]),
            row("Memory", health["ram_percent"]),
            row("Disk", health["disk_percent"], 80, 90) + f" ({esc(health.get('disk_path') or '/')})",
            f"🌡 CPU temperature: {temp_text}",
        ]
        load = health.get("load_average")
        if load:
            lines.append(f"⚖️ Load: {' / '.join(f'{value:.2f}' for value in load)} (1/5/15 min)")
        return Reply("\n".join(lines), [[("🗄 Disks", "c:/disk"), ("⏱ Uptime", "c:/uptime"), ("📈 Containers", "c:/stats")]])

    def _alerts(self) -> Reply:
        active = self.status_service.active_alerts()
        buttons: Buttons = [self._silence_buttons()]
        if not active:
            text = "✅ <b>No active alerts</b>\nNothing needs your attention right now."
            if silence_active(self.state):
                text += "\n\n🔕 Notifications are silenced. Use /resume."
            return Reply(text, buttons)
        now = time.time()
        titles = self._alert_titles()
        lines = [f"🚨 <b>{len(active)} active alert{'s' if len(active) != 1 else ''}</b>", ""]
        for alert_id in active[:30]:
            since = self.state.get(f"alerts.{alert_id}.active_since")
            age = f" - firing for {human_duration(now - float(since))}" if since else ""
            title = titles.get(alert_id)
            label = f"{esc(title)} <i>({esc(alert_id)})</i>" if title else esc(alert_id)
            lines.append(f"• {label}{age}")
        if silence_active(self.state):
            lines.extend(["", "🔕 Notifications are silenced. Use /resume."])
        buttons.append([("🗒 Recent events", "c:/events"), ("📋 Status", "c:/status")])
        return Reply("\n".join(lines), buttons)

    def _events(self, args: list[str]) -> Reply:
        count = clamp_count(args[0] if args else None, DEFAULT_EVENTS, MAX_EVENTS)
        events = self.status_service.history.recent(count)
        if not events:
            return Reply("🗒 No events recorded yet.")
        icons = {"active": "🚨", "recovered": "✅", "changed": "🔄", "event": "ℹ️"}
        lines = [f"🗒 <b>Last {len(events)} events</b>", "<i>Newest first, times in UTC</i>", ""]
        for event in events:
            stamp = str(event.get("ts", ""))[:16].replace("T", " ")
            # Titles are capped so 30 events always fit one message without cutting a tag in half.
            title = str(event.get("title") or "")[:100]
            lines.append(f"{icons.get(event.get('status'), '•')} <code>{esc(stamp[5:])}</code> {esc(title)}")
        return Reply("\n".join(lines), [[("🚨 Active alerts", "c:/alerts")]])

    def _uptime(self) -> Reply:
        host = self.status_service.host()
        load = host.get("load_average")
        load_text = " / ".join(f"{value:.2f}" for value in load) if load else "unavailable"
        return Reply(
            "\n".join(
                [
                    "⏱ <b>Uptime</b>",
                    "",
                    f"🖥 Host: {human_duration(host['uptime_seconds'])}",
                    f"🐕 Sheltie: {human_duration(host['sheltie_uptime_seconds'])}",
                    f"⚖️ Load (1/5/15m): {load_text} on {host.get('cpu_count') or '?'} CPUs",
                    f"🔁 Swap: {human_bytes(host['swap_used'])} of {human_bytes(host['swap_total'])} ({host['swap_percent']:.0f}%)",
                ]
            )
        )

    def _disk(self) -> Reply:
        lines = ["🗄 <b>Disks</b>", ""]
        for disk in self.status_service.disks():
            if "error" in disk:
                lines.append(f"❔ {esc(disk['path'])}: {esc(disk['error'])}")
                continue
            lines.append(
                f"{usage_icon(disk['percent'], 80, 90)} <code>{usage_bar(disk['percent'])}</code> {disk['percent']:.0f}% {esc(disk['path'])} "
                f"({human_bytes(disk['free'])} free of {human_bytes(disk['total'])})"
            )
        return Reply("\n".join(lines))

    def _version(self) -> Reply:
        status = self.status_service.status()
        started = str(status.get("started_at", ""))[:16].replace("T", " ")
        return Reply(f"🐕 <b>Sheltie {esc(__version__)}</b>\nRunning since {esc(started)} UTC")

    # ---- power -------------------------------------------------------------------

    @staticmethod
    def _supply_line(power: dict[str, Any]) -> str:
        battery = power.get("battery_percent")
        battery_text = ""
        if battery is not None:
            status = str(power.get("battery_status") or "").lower()
            battery_text = f" · battery {battery}%" + (f" ({esc(status)})" if status and status != "unknown" else "")
        if power.get("ac_online") is True:
            return f"🔌 On AC power{battery_text}"
        if power.get("ac_online") is False:
            return f"🔋 <b>Running on battery</b>{battery_text}"
        return f"❔ Power source unknown{battery_text}"

    @staticmethod
    def _recovery_line(recovery: dict[str, Any]) -> str:
        mode = recovery.get("mode")
        if mode == "on":
            return "✅ Power on with AC: on"
        if mode == "last":
            return "✅ Power on with AC: last state"
        if mode == "off":
            return "⚠️ Power on with AC: off · /autoon on"
        return "❔ Power on with AC: unknown"

    def _power(self) -> Reply:
        power = self.status_service.power()
        recovery = power.get("ac_recovery") or {}
        machine = " ".join(str(part) for part in (power.get("vendor"), power.get("model")) if part)
        on_battery = power.get("ac_online") is False
        lines = ["🔋 <b>Running on battery</b>" if on_battery else "🔌 <b>Power</b>"]
        if machine:
            lines.append(f"<i>{esc(machine)}</i>")
        lines += ["", self._supply_line(power), ""]
        lines += self._recovery_details(recovery)
        return Reply("\n".join(lines), self._recovery_buttons(recovery))

    @staticmethod
    def _recovery_details(recovery: dict[str, Any]) -> list[str]:
        if not recovery.get("supported"):
            return ["❔ <b>Power on with AC: not available</b>", esc(recovery.get("reason") or "This machine does not expose the setting.")]
        mode = recovery.get("mode")
        offered = ", ".join(recovery.get("modes") or [])
        if mode == "on":
            details = ["✅ <b>Power on with AC: on</b>", "After a power cut, this machine starts by itself when power returns."]
        elif mode == "last":
            details = ["✅ <b>Power on with AC: last state</b>", "After a power cut, this machine goes back to how it was (on if it was running)."]
        elif mode == "off":
            details = [
                "⚠️ <b>Power on with AC: off</b>",
                "After a power cut, this machine stays off until someone presses the power button.",
                "Turn it on with /autoon on.",
            ]
        else:
            details = ["❔ <b>Power on with AC: unknown</b>", esc(recovery.get("reason") or "Sheltie could not read the BIOS setting.")]
        details.append(f"<i>BIOS setting: AC power recovery ({esc(offered)})</i>")
        return details

    @staticmethod
    def _recovery_buttons(recovery: dict[str, Any]) -> Buttons:
        if not recovery.get("supported"):
            return []
        if recovery.get("mode") == "off":
            return [[("⚡ Turn on power-on with AC", "c:/autoon on")]]
        if recovery.get("mode") in ("on", "last") and "off" in (recovery.get("modes") or []):
            return [[("Turn off", "c:/autoon off"), ("🔄 Refresh", "c:/power")]]
        return [[("🔄 Refresh", "c:/power")]]

    def _autoon(self, args: list[str]) -> Reply:
        if not args:
            return self._power()
        mode = args[0].lower()
        if mode in ("enable", "enabled", "true", "1", "yes"):
            mode = "on"
        elif mode in ("disable", "disabled", "false", "0", "no"):
            mode = "off"
        if mode not in ("on", "off", "last"):
            return Reply("Usage: /autoon [on|off]\nShows or changes whether this machine powers on by itself when AC power returns.")
        result = self.action_service.set_ac_recovery(mode)
        recovery = result.get("ac_recovery") or {}
        if not result["ok"]:
            return Reply(f"⚠️ <b>Could not change power on with AC</b>\n{esc(result['error'])}")
        return Reply("\n".join([f"⚡ {esc(result['message'])}.", ""] + self._recovery_details(recovery)), self._recovery_buttons(recovery))

    # ---- network -----------------------------------------------------------------

    def _network(self) -> Reply:
        network = self.status_service.network()
        internet = network["internet_up"]
        headline = {True: "🌐 <b>Online</b>", False: "❌ <b>Internet is unreachable</b>"}.get(internet, "❔ <b>Checking the connection…</b>")
        lines = [headline, f"Traffic leaves through {esc(network['default_route_label'])}", ""]
        for label, status in network["interfaces"].items():
            details = f"link {'yes' if status['carrier'] else 'no'} · IPv4 {'yes' if status['has_ip'] else 'no'} · {esc(status['operstate'])}"
            lines.append(f"{state_icon(status['up'])} <b>{esc(label.title())}</b> {esc(status['name'])}: {'up' if status['up'] else 'down'}")
            lines.append(f"    <i>{details}</i>")
        if not network["interfaces"]:
            lines.append("No interfaces configured. Add network.ethernet or network.wifi to config.yml.")
        return Reply("\n".join(lines), [[("🧭 Addresses", "c:/ip"), ("📶 Ping 1.1.1.1", "c:/ping 1.1.1.1")]])

    def _ip(self) -> Reply:
        lines = ["🧭 <b>Addresses</b>", ""]
        for interface, ips in self.status_service.addresses().items():
            lines.append(f"• {esc(interface)}: <code>{esc(', '.join(ips))}</code>")
        address = public_ip()
        lines.append(f"🌍 Public: <code>{esc(address)}</code>" if address else "🌍 Public: unavailable")
        return Reply("\n".join(lines))

    def _ping(self, args: list[str]) -> Reply:
        if not args:
            return Reply("Usage: /ping host", [[("1.1.1.1", "c:/ping 1.1.1.1"), ("8.8.8.8", "c:/ping 8.8.8.8")]])
        try:
            stats = ping_stats(args[0])
        except ValueError as exc:
            return Reply(f"⚠️ {esc(exc)}")
        if stats.get("avg_ms") is None:
            return Reply(f"❌ <b>{esc(stats['host'])}</b>: no reply ({esc(stats.get('error', 'unreachable'))})")
        loss = stats.get("loss_percent")
        loss_text = f", loss {loss:.0f}%" if loss is not None else ""
        return Reply(
            f"{state_icon(stats['ok'])} <b>{esc(stats['host'])}</b>: avg {stats['avg_ms']:.1f}ms "
            f"(min {stats['min_ms']:.1f} / max {stats['max_ms']:.1f}){loss_text}"
        )

    # ---- containers --------------------------------------------------------------

    def _docker(self) -> Reply:
        docker_status = self.status_service.docker()
        if not docker_status["available"]:
            return Reply(f"🐳 <b>Docker isn't reachable</b>\n{esc(docker_status['error'])}")

        containers = docker_status["containers"]
        if not containers:
            return Reply("🐳 <b>No containers found</b>")

        running = [entry for entry in containers if entry["status"] == "running"]
        stopped = [entry for entry in containers if entry["status"] != "running"]
        lines = [f"🐳 <b>{len(running)} of {len(containers)} containers running</b>"]
        buttons: Buttons = []
        if stopped:
            lines += ["", "<b>Not running</b>"]
            for entry in stopped[:MAX_LIST_ITEMS]:
                note = " · stopped on purpose" if entry.get("user_stopped") else ""
                lines.append(f"⚠️ {esc(entry['name'])}: {esc(entry['status'])}{note}")
                if not entry.get("blocked") and len(buttons) < 6:
                    buttons.append([(f"▶️ Start {entry['name']}", f"c:/start {entry['name']}"), ("📜 Logs", f"c:/logs {entry['name']}")])
        if running:
            lines += ["", "<b>Running</b>"]
            for entry in running[:MAX_LIST_ITEMS]:
                lines.append(f"✅ {esc(entry['name'])}" + (" · protected" if entry.get("blocked") else ""))
            if len(running) > MAX_LIST_ITEMS:
                lines.append(f"…and {len(running) - MAX_LIST_ITEMS} more")
        buttons.append([("📈 Stats", "c:/stats"), ("🔁 Restart…", "c:/restart"), ("🩹 Auto-heal", "c:/heal")])
        return Reply("\n".join(lines), buttons)

    def _stats(self, args: list[str]) -> Reply:
        usage = self.status_service.container_stats(args[0] if args else None)
        if not usage:
            return Reply("🐳 No running containers.")
        rows = [row for row in usage if "error" not in row]
        rows.sort(key=lambda row: (row["cpu_percent"], row["memory_used"]), reverse=True)
        title = f"📈 <b>{esc(args[0])}</b>" if args else f"📈 <b>Top {min(5, len(rows))} containers by CPU</b>"
        lines = [title, ""]
        for row in rows[: 1 if args else 5]:
            memory = human_bytes(row["memory_used"])
            if row.get("memory_percent") is not None:
                memory += f" ({row['memory_percent']:.0f}%)"
            lines.append(f"• <b>{esc(row['name'])}</b>: CPU {row['cpu_percent']:.1f}% · RAM {memory}")
        for row in usage:
            if "error" in row:
                lines.append(f"• {esc(row['name'])}: unavailable ({esc(row['error'])})")
        return Reply("\n".join(lines))

    def _logs(self, args: list[str]) -> Reply:
        if not args:
            return self._picker("/logs", "Show logs for which container?", lambda _entry: True)
        name = args[0]
        lines = clamp_count(args[1] if len(args) > 1 else None, DEFAULT_LOG_LINES, MAX_LOG_LINES)
        output = redact(self.status_service.container_logs(name, lines), self.notifier.bot_token).strip()
        if not output:
            return Reply(f"📜 {esc(name)}: no log output.")
        header = f"📜 <b>{esc(name)}</b> (last {lines} lines)\n"
        body = tail_text(output, MAX_MESSAGE_CHARS - len(header) - 200)
        return Reply(f"{header}<pre>{esc(body)}</pre>", [[("🔄 Refresh", f"c:/logs {name} {lines}"), ("🔁 Restart", f"c:/restart {name}")]])

    def _restart(self, args: list[str]) -> Reply:
        if not args:
            return self._picker("/restart", "Restart which container?", lambda entry: entry.get("status") == "running")
        result = self.action_service.restart_container(args[0])
        if result["ok"]:
            return Reply(f"🔁 <b>Restarted {esc(args[0])}</b>\n{esc(result['message'])}", [[("📜 Logs", f"c:/logs {args[0]}"), ("🐳 Containers", "c:/docker")]])
        return Reply(f"⚠️ <b>Docker restart failed</b>\n{esc(result['error'])}")

    def _start(self, args: list[str]) -> Reply:
        if not args:
            return Reply(
                "🐕 <b>Hi, this is Sheltie</b>\nI keep watch over this server and tell you when something needs attention.\n\n"
                "Tap a button below, or send /help for every command.",
                self._menu().buttons,
            )
        result = self.action_service.start_container(args[0])
        if result["ok"]:
            # A manual start means the operator wants it running again.
            stopped = set(self.state.get(USER_STOPPED_KEY, []))
            stopped.discard(args[0])
            self.state.set(USER_STOPPED_KEY, sorted(stopped))
            return Reply(f"▶️ <b>Container started</b>\n{esc(result['message'])}", [[("📜 Logs", f"c:/logs {args[0]}"), ("🐳 Containers", "c:/docker")]])
        return Reply(f"⚠️ <b>Container start failed</b>\n{esc(result['error'])}")

    def _stop(self, args: list[str]) -> Reply:
        if not args:
            return self._picker("/stop", "Stop which container?", lambda entry: entry.get("status") == "running")
        result = self.action_service.stop_container(args[0])
        if result["ok"]:
            return Reply(f"⏹ <b>Container stopped</b>\n{esc(result['message'])}", [[(f"▶️ Start {args[0]}", f"c:/start {args[0]}")]])
        return Reply(f"⚠️ <b>Container stop failed</b>\n{esc(result['error'])}")

    def _heal(self) -> Reply:
        status = self.status_service.status()
        heal = status.get("auto_heal") or {}
        if not heal.get("enabled"):
            return Reply("🩹 <b>Auto-heal is off</b>\nTurn it on with auto_heal.enabled in config.yml.")
        watched = list(heal.get("active_containers") or [])
        interfaces = list(heal.get("active_network_interfaces") or [])
        user_stopped = list(self.state.get(USER_STOPPED_KEY, []))
        lines = [f"🩹 <b>Auto-heal watches {len(watched)} container{'s' if len(watched) != 1 else ''}</b>", f"<i>Checks every {esc(heal.get('interval'))}s</i>"]
        if watched:
            lines += ["", "<b>Restarted if they stop</b>", esc(", ".join(watched[:40]))]
        if interfaces:
            lines += ["", "<b>Network interfaces</b>", esc(", ".join(interfaces))]
        if user_stopped:
            lines += ["", "<b>Stopped on purpose (left alone)</b>", esc(", ".join(user_stopped))]
        return Reply("\n".join(lines))

    # ---- websites ----------------------------------------------------------------

    def _sites(self) -> Reply:
        sites = self.status_service.sites()
        if not sites["sites"]:
            return Reply("🌍 <b>No website monitors yet</b>\nAdd one with /addsite name https://example.com")

        down = [site for site in sites["sites"] if site.get("up") is False]
        headline = f"🌍 <b>{sites['up']} of {sites['total']} sites up</b>"
        lines = [headline if not down else f"🔴 <b>{len(down)} site{'s' if len(down) != 1 else ''} down</b> · {sites['up']} of {sites['total']} up", ""]
        ordered = sorted(sites["sites"], key=lambda site: site.get("up") is not False)
        for site in ordered[:MAX_LIST_ITEMS]:
            latency = site.get("latency_ms")
            details = f"{latency}ms" if latency is not None else "no response"
            if site.get("status_code"):
                details = f"{site['status_code']} · {details}"
            lines.append(f"{state_icon(site.get('up'))} <b>{esc(site['name'])}</b> <i>{esc(details)}</i>")
        if len(sites["sites"]) > MAX_LIST_ITEMS:
            lines.append(f"…and {len(sites['sites']) - MAX_LIST_ITEMS} more")
        buttons: Buttons = [[(f"🔎 Check {site['name']}", f"c:/checksite {site['name']}")] for site in down[:4]]
        buttons.append([("🔄 Refresh", "c:/sites")])
        return Reply("\n".join(lines), buttons)

    def _add_site(self, args: list[str]) -> Reply:
        if len(args) < 2:
            return Reply("Usage: /addsite name https://example.com")
        result = self.action_service.add_site({"name": args[0], "url": args[1]})
        if result["ok"]:
            return Reply(f"🌍 <b>Site monitor added</b>\n{esc(result['message'])}", [[(f"🔎 Check {args[0]}", f"c:/checksite {args[0]}")]])
        return Reply(f"⚠️ <b>Site monitor add failed</b>\n{esc(result['error'])}")

    def _remove_site(self, name: str) -> Reply:
        result = self.action_service.remove_site(name)
        if result["ok"]:
            return Reply(f"🗑 <b>Site monitor removed</b>\n{esc(result['message'])}")
        return Reply(f"⚠️ <b>Site monitor remove failed</b>\n{esc(result['error'])}")

    def _checksite(self, args: list[str]) -> Reply:
        query = " ".join(args).strip().strip("\"'")
        sites = configured_sites(self.config, self.state)
        if not query:
            buttons: Buttons = [[(str(site.get("name")), f"c:/checksite {site.get('name')}")] for site in sites[:MAX_PICKER_BUTTONS]]
            return Reply("Usage: /checksite name\nOr tap a site:", buttons)
        match = next((site for site in sites if str(site.get("name", "")).lower() == query.lower()), None)
        if match is None:
            names = ", ".join(str(site.get("name")) for site in sites) or "none"
            return Reply(f"⚠️ No site called {esc(query)}. Monitored sites: {esc(names)}")
        result = probe_site(match)
        if result is None:
            return Reply(f"⚠️ {esc(query)} has no URL configured.")
        lines = [
            f"{state_icon(result['up'])} <b>{esc(result['name'])} is {'up' if result['up'] else 'down'}</b>",
            "",
            f"<b>URL:</b> {esc(result['url'])}",
            f"<b>Status:</b> {esc(result['status_code'] or 'none')} (expected {esc(', '.join(str(code) for code in result['expected_status']))})",
            f"<b>Latency:</b> {esc(result['latency_ms'])}ms",
        ]
        if result["error"]:
            lines.append(f"<b>Error:</b> {esc(result['error'])}")
        return Reply("\n".join(lines), [[("🔄 Check again", f"c:/checksite {result['name']}")]])

    # ---- alerts and host actions -------------------------------------------------

    def _clear_cache(self) -> Reply:
        result = self.action_service.clear_ram_cache()
        if result["ok"]:
            return Reply(f"🧹 <b>RAM cache cleared</b>\n{esc(result['message'])}")
        return Reply(f"⚠️ <b>RAM cache clear failed</b>\n{esc(result['error'])}")

    def _silence(self, args: list[str]) -> Reply:
        minutes = None
        if args:
            try:
                seconds = parse_duration(args[0])
            except ValueError:
                return Reply("Usage: /silence [30m|2h|1d]")
            if seconds <= 0:
                return Reply("Usage: /silence [30m|2h|1d]")
            minutes = seconds / 60
        result = self.action_service.silence_alerts(minutes)
        if not result["ok"]:
            return Reply(f"⚠️ <b>Silence failed</b>\n{esc(result['error'])}")
        buttons: Buttons = [[("🔔 Resume alerts", "c:/resume")]]
        if minutes:
            return Reply(f"🔕 <b>Alerts silenced for {human_duration(minutes * 60)}</b>\nThey resume by themselves, or use /resume.", buttons)
        return Reply("🔕 <b>Alerts silenced</b>\nUse /resume to turn them back on.", buttons)

    def _resume(self) -> Reply:
        result = self.action_service.resume_alerts()
        if not result["ok"]:
            return Reply(f"⚠️ <b>Resume failed</b>\n{esc(result['error'])}")
        return Reply("🔔 <b>Alerts resumed</b>", [[("🚨 Active alerts", "c:/alerts")]])
