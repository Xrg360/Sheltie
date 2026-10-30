"""Names on your tailnet: where each one points, and keeping DNS + the proxy in step.

A name like sheltie.home.internals gets an A record in a zone that CoreDNS serves on
this server's Tailscale IP, and (when it points at an app) a proxy host in Nginx Proxy
Manager that forwards to the app's port.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from monitors.config import env
from monitors.names import dns, ports
from monitors.names.db import Database
from monitors.names.discovery import Docker, DockerError
from monitors.names.npm import PATHS, Npm, NpmError
from monitors.names.tailscale import Tailscale, TailscaleError

HOSTNAME = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?)*$")
ACL_NAME = "Sheltie: Tailscale devices only"
TAILNET_RANGES = ("100.64.0.0/10", "fd7a:115c:a1e0::/48")
WELL_KNOWN = {22: "SSH", 25: "SMTP", 631: "Printing (CUPS)", 3306: "MySQL", 5432: "PostgreSQL", 6379: "Redis"}
# The DNS sidecar is part of the names machinery itself, never offered as a target.
OWN_CONTAINERS = ("sheltie-dns",)
# Fields of an NPM proxy host that Sheltie owns; anything else set in NPM is left alone.
PROXY_FIELDS = ("domain_names", "forward_scheme", "forward_host", "forward_port",
                "access_list_id", "allow_websocket_upgrade", "block_exploits")
REACHABILITY_TTL = 30.0
# Settings carried over when importing a names database.
IMPORTED_SETTINGS = ("domain_label", "domain_tld", "tailnet_only", "npm_acl_id", "dns_serial",
                     "last_server_ip", "last_server_dns", "last_server_name")


class UserError(Exception):
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class ServerInfo:
    hostname: str
    dns_name: str
    ip: str
    error: str | None = None


@dataclass(frozen=True)
class NamesConfig:
    enabled: bool
    data_dir: str
    default_domain: str
    npm_url: str
    npm_email: str
    npm_password: str
    npm_container: str
    tailscale_socket: str
    # Address the DNS server binds to. Empty means "this server's Tailscale IPv4".
    dns_bind: str
    # Overrides the Tailscale IPv4 of this server (tests, or no Tailscale socket).
    server_ip: str
    # Where the CoreDNS container sees the files written to <data_dir>/dns.
    coredns_dir: str
    sync_seconds: int = 300

    @property
    def dns_dir(self) -> str:
        return os.path.join(self.data_dir, "dns")

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "names.db")

    @classmethod
    def from_config(cls, config: dict[str, Any], data_dir: str = "state") -> "NamesConfig":
        section = config.get("names") or {}

        def pick(key: str, default: str = "") -> str:
            # SHELTIE_NAMES_<KEY> wins over config.yml, so secrets can stay in .env.
            return str(env(f"NAMES_{key.upper()}") or section.get(key) or default).strip()

        enabled_env = env("NAMES_ENABLED")
        enabled = enabled_env.lower() in ("1", "true", "yes", "on") if enabled_env else section.get("enabled") is True
        return cls(
            enabled=enabled,
            data_dir=data_dir,
            default_domain=pick("domain", "home.internals").lower(),
            npm_url=pick("npm_url", "http://127.0.0.1:81").rstrip("/"),
            npm_email=pick("npm_email"),
            npm_password=pick("npm_password"),
            npm_container=pick("npm_container", "npm"),
            tailscale_socket=pick("tailscale_socket", "/var/run/tailscale/tailscaled.sock"),
            dns_bind=pick("dns_bind"),
            server_ip=pick("server_ip"),
            coredns_dir=pick("coredns_dir", "/dns"),
            sync_seconds=max(60, int(pick("sync_seconds", "300") or 300)),
        )


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


class NamesService:
    def __init__(self, cfg: NamesConfig, db: Database, ts: Any, docker: Any, npm: Any,
                 on_change: Callable[[str, str], None] | None = None) -> None:
        self.cfg = cfg
        self.db = db
        self.ts = ts
        self.docker = docker
        self.npm = npm
        # Called with (title, body) after every change, so it lands in Sheltie's event history.
        self.on_change = on_change or (lambda title, body: None)
        self.lock = threading.RLock()
        self._last_sync: dict[str, Any] | None = None
        self._reach: tuple[float, dict[int, dict[str, Any]]] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- where we are ------------------------------------------------------------

    def server(self) -> ServerInfo:
        try:
            s = self.ts.server()
            info = ServerInfo(s.hostname, s.dns_name, self.cfg.server_ip or s.ip)
            if info.ip:
                self.db.set_setting("last_server_ip", info.ip)
                self.db.set_setting("last_server_dns", info.dns_name)
                self.db.set_setting("last_server_name", info.hostname)
            return info
        except TailscaleError as exc:
            return ServerInfo(
                hostname=self.db.get_setting("last_server_name", "this server"),
                dns_name=self.db.get_setting("last_server_dns"),
                ip=self.cfg.server_ip or self.db.get_setting("last_server_ip"),
                error=str(exc),
            )

    def bind_ip(self) -> str:
        return self.cfg.dns_bind or self.server().ip

    # --- domain ------------------------------------------------------------------

    def domain(self) -> tuple[str, str]:
        default_label, _, default_tld = self.cfg.default_domain.rpartition(".")
        return (self.db.get_setting("domain_label", default_label or "home"),
                self.db.get_setting("domain_tld", default_tld or "internals"))

    def zone(self) -> str:
        label, tld = self.domain()
        return f"{label}.{tld}" if label else tld

    def fqdn(self, name: str) -> str:
        return f"{name}.{self.zone()}"

    # --- lifecycle -----------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="names-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        last_ip = ""
        first = True
        while first or not self._stop.wait(self.cfg.sync_seconds):
            first = False
            try:
                ip = self.server().ip
                if ip and ip != last_ip:
                    self.write_dns()
                    last_ip = ip
                self.sync()
            except Exception:  # Never let the background loop die.
                logging.exception("Names: background sync failed")

    # --- payloads ------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        label, tld = self.domain()
        server = self.server()
        reach = self.reachability()
        records = self.records()
        for r in records:
            r["reachable"] = reach.get(r["id"], {"ok": None, "why": None})
        return {
            "enabled": True,
            "zone": self.zone(),
            "domain": {"label": label, "tld": tld},
            "server": {"name": server.hostname, "ip": server.ip, "dns_name": server.dns_name, "error": server.error},
            "records": records,
            "tailnet_only": self.tailnet_only(),
            "npm_configured": self.npm.configured,
            "last_sync": self._last_sync,
        }

    def records(self) -> list[dict[str, Any]]:
        rows = self.db.all("SELECT * FROM records ORDER BY name")
        server_ip = self.server().ip
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "fqdn": self.fqdn(r["name"]),
                "kind": r["kind"],
                "url": f"http://{self.fqdn(r['name'])}",
                "points_to": server_ip if r["kind"] == "proxy" else r["target_host"],
                "target_host": r["target_host"],
                "target_port": r["target_port"],
                "scheme": r["scheme"],
                "websockets": bool(r["websockets"]),
                "source": r["source"],
                "label": r["label"],
                "synced": r["npm_id"] is not None or r["kind"] == "device",
                "sync_error": r["sync_error"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    # --- records -----------------------------------------------------------------

    def _clean(self, data: dict[str, Any], record_id: int | None) -> dict[str, Any]:
        name = str(data.get("name", "")).strip().lower()
        err = dns.label_error(name)
        if err:
            raise UserError(err, field="name")
        if name in dns.RESERVED:
            raise UserError(f"“{name}” is reserved for the DNS server itself.", field="name")
        clash = self.db.one("SELECT id FROM records WHERE name = ?", (name,))
        if clash and clash["id"] != record_id:
            raise UserError(f"{self.fqdn(name)} already exists.", field="name")

        mode = data.get("mode")
        host = str(data.get("host", "")).strip().lower()
        raw_port = data.get("port")
        port = None
        if raw_port not in (None, ""):
            try:
                port = int(str(raw_port))
            except (TypeError, ValueError):
                port = 0
            if not 0 < port < 65536:
                raise UserError("Port must be a number from 1 to 65535.", field="port")
        scheme = data.get("scheme") or "http"
        if scheme not in ("http", "https"):
            raise UserError("Scheme must be http or https.", field="scheme")

        if mode == "app":
            if not host or not (HOSTNAME.match(host) or _is_ip(host)):
                raise UserError("Pick an app, or enter a valid host.", field="host")
            if port is None:
                raise UserError("Enter the port the app listens on.", field="port")
            kind = "proxy"
        elif mode == "device":
            if not _is_ip(host):
                raise UserError("Pick a Tailscale device.", field="host")
            kind = "proxy" if port else "device"
        else:
            raise UserError("Choose where the name should point.", field="mode")
        return {
            "name": name,
            "kind": kind,
            "target_host": host,
            "target_port": port,
            "scheme": scheme,
            "websockets": 1 if data.get("websockets", True) else 0,
            "source": str(data.get("source", ""))[:120],
            "label": str(data.get("label", ""))[:120],
        }

    def _record_id(self, data: dict[str, Any]) -> int:
        try:
            return int(str(data.get("id")))
        except (TypeError, ValueError):
            raise UserError("That name doesn't exist any more.") from None

    def create_record(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            clean = self._clean(data, None)
            now = int(time.time())
            cur = self.db.execute(
                "INSERT INTO records (name, kind, target_host, target_port, scheme, websockets, source, label, "
                "created_at, updated_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'sheltie')",
                (clean["name"], clean["kind"], clean["target_host"], clean["target_port"], clean["scheme"],
                 clean["websockets"], clean["source"], clean["label"], now, now),
            )
            self.on_change(f"Name added: {self.fqdn(clean['name'])}", f"{self.fqdn(clean['name'])} → {self._describe(clean)}")
            self._changed()
            return self._record(cur.lastrowid)

    def update_record(self, data: dict[str, Any]) -> dict[str, Any]:
        record_id = self._record_id(data)
        with self.lock:
            old = self.db.one("SELECT * FROM records WHERE id = ?", (record_id,))
            if not old:
                raise UserError("That name doesn't exist any more.")
            clean = self._clean(data, record_id)
            self.db.execute(
                "UPDATE records SET name = ?, kind = ?, target_host = ?, target_port = ?, scheme = ?, websockets = ?, "
                "source = ?, label = ?, updated_at = ? WHERE id = ?",
                (clean["name"], clean["kind"], clean["target_host"], clean["target_port"], clean["scheme"],
                 clean["websockets"], clean["source"], clean["label"], int(time.time()), record_id),
            )
            self.on_change(f"Name changed: {self.fqdn(clean['name'])}",
                           f"{self.fqdn(old['name'])} → {self._describe(old)}\nis now\n"
                           f"{self.fqdn(clean['name'])} → {self._describe(clean)}")
            self._changed()
            return self._record(record_id)

    def delete_record(self, data: dict[str, Any]) -> dict[str, Any]:
        record_id = self._record_id(data)
        with self.lock:
            old = self.db.one("SELECT * FROM records WHERE id = ?", (record_id,))
            if not old:
                raise UserError("That name doesn't exist any more.")
            if old["npm_id"] is not None:
                self.db.execute("INSERT OR IGNORE INTO npm_garbage (npm_kind, npm_id) VALUES (?, ?)",
                                (old["npm_kind"], old["npm_id"]))
            self.db.execute("DELETE FROM records WHERE id = ?", (record_id,))
            self.on_change(f"Name removed: {self.fqdn(old['name'])}", f"{self.fqdn(old['name'])} → {self._describe(old)}")
            self._changed()
            return {"name": old["name"], "fqdn": self.fqdn(old["name"])}

    def _changed(self) -> None:
        self._reach = None
        self.write_dns()
        self.sync()

    def _record(self, record_id: int | None) -> dict[str, Any]:
        return next(r for r in self.records() if r["id"] == record_id)

    @staticmethod
    def _describe(r: dict[str, Any]) -> str:
        target = r["target_host"] + (f":{r['target_port']}" if r.get("target_port") else "")
        return f"{r['label']} ({target})" if r.get("label") else target

    # --- DNS ---------------------------------------------------------------------

    def write_dns(self) -> None:
        server_ip = self.server().ip
        bind = self.bind_ip()
        if not server_ip or not bind:
            return  # No Tailscale address yet; keep the last good files.
        entries = []
        for r in self.db.all("SELECT name, kind, target_host FROM records ORDER BY name"):
            entries.append((r["name"], r["target_host"] if r["kind"] == "device" else server_ip))
        serial = max(int(time.time()), int(self.db.get_setting("dns_serial", "0")) + 1)
        self.db.set_setting("dns_serial", str(serial))
        dns.write_coredns(self.cfg.dns_dir, self.cfg.coredns_dir, self.zone(), bind, entries, serial, server_ip)

    # --- proxy (Nginx Proxy Manager) ---------------------------------------------

    def tailnet_only(self) -> bool:
        return self.db.get_setting("tailnet_only", "1") == "1"

    def _ensure_acl(self) -> int:
        body = {
            "name": ACL_NAME,
            "satisfy_any": False,
            "pass_auth": False,
            "items": [],
            "clients": [{"directive": "allow", "address": r} for r in TAILNET_RANGES],
        }
        acl_id = int(self.db.get_setting("npm_acl_id", "0") or 0)
        current = self.npm.get("access", acl_id) if acl_id else None
        if current is None:
            mine = [a for a in self.npm.request("GET", PATHS["access"]) or [] if a.get("name") == ACL_NAME]
            current = mine[0] if mine else self.npm.create("access", body)
            acl_id = current["id"]
            self.db.set_setting("npm_acl_id", str(acl_id))
        if current.get("name") != ACL_NAME:
            # An imported list keeps its id and rules but gets Sheltie's name.
            self.npm.update("access", acl_id, body)
        return acl_id

    def _desired(self, r: dict[str, Any], acl_id: int) -> dict[str, Any] | None:
        if r["kind"] != "proxy":
            return None
        return {
            "domain_names": [self.fqdn(r["name"])],
            "forward_scheme": r["scheme"],
            "forward_host": r["target_host"],
            "forward_port": r["target_port"],
            "access_list_id": acl_id,
            "allow_websocket_upgrade": bool(r["websockets"]),
            "block_exploits": True,
            "certificate_id": 0,
            "ssl_forced": False,
            "caching_enabled": False,
            "http2_support": False,
            "hsts_enabled": False,
            "hsts_subdomains": False,
            "advanced_config": "",
            "locations": [],
            "meta": {},
        }

    @staticmethod
    def _differs(current: dict[str, Any], body: dict[str, Any]) -> bool:
        for f in PROXY_FIELDS:
            have, want = current.get(f), body.get(f)
            if isinstance(want, bool):
                have = bool(have)
            if have != want:
                return True
        return not current.get("enabled", True)

    def sync(self) -> dict[str, Any]:
        """Make NPM match the records. Safe to run any time; it only changes what differs."""
        with self.lock:
            rows = self.db.all("SELECT * FROM records")
            needs_proxy = [r for r in rows if r["kind"] == "proxy"]
            if not self.npm.configured:
                msg = "Nginx Proxy Manager isn't connected yet, so this name resolves but doesn't open a page."
                for r in needs_proxy:
                    self.db.execute("UPDATE records SET sync_error = ? WHERE id = ?", (msg, r["id"]))
                self._last_sync = {"at": int(time.time()), "ok": False, "error": msg}
                return self._last_sync
            try:
                acl_id = self._ensure_acl() if self.tailnet_only() else 0
                owned = self.npm.request("GET", PATHS["proxy"]) or []
            except NpmError as exc:
                msg = f"Couldn't update Nginx Proxy Manager: {exc}"
                for r in needs_proxy:
                    self.db.execute("UPDATE records SET sync_error = ? WHERE id = ?", (msg, r["id"]))
                self._last_sync = {"at": int(time.time()), "ok": False, "error": msg}
                return self._last_sync

            for g in self.db.all("SELECT * FROM npm_garbage"):
                try:
                    self.npm.delete(g["npm_kind"], g["npm_id"])
                    self.db.execute("DELETE FROM npm_garbage WHERE npm_kind = ? AND npm_id = ?",
                                    (g["npm_kind"], g["npm_id"]))
                except NpmError:
                    pass  # Try again next sync.

            errors = 0
            for r in rows:
                body = self._desired(r, acl_id)
                npm_kind, npm_id = r["npm_kind"], r["npm_id"]
                try:
                    if npm_id is not None and (body is None or npm_kind != "proxy"):
                        self.npm.delete(npm_kind, npm_id)
                        npm_kind = npm_id = None
                    if body:
                        current = self.npm.get("proxy", npm_id) if npm_id is not None else None
                        if current is None:
                            # Adopt a host made earlier but lost track of, before creating a duplicate.
                            current = next((h for h in owned if h.get("domain_names") == body["domain_names"]), None)
                        if current is None:
                            current = self.npm.create("proxy", body)
                        elif self._differs(current, body):
                            self.npm.update("proxy", current["id"], body)
                            if not current.get("enabled", True):
                                self.npm.request("POST", f"{PATHS['proxy']}/{current['id']}/enable")
                        npm_kind, npm_id = "proxy", current["id"]
                    self.db.execute("UPDATE records SET npm_kind = ?, npm_id = ?, sync_error = NULL WHERE id = ?",
                                    (npm_kind, npm_id, r["id"]))
                except NpmError as exc:
                    errors += 1
                    self.db.execute("UPDATE records SET npm_kind = ?, npm_id = ?, sync_error = ? WHERE id = ?",
                                    (npm_kind, npm_id, str(exc), r["id"]))
            self._last_sync = {"at": int(time.time()), "ok": errors == 0,
                               "error": f"{errors} name(s) couldn't be updated in Nginx Proxy Manager." if errors else None}
            return self._last_sync

    # --- settings ------------------------------------------------------------------

    def change_domain(self, data: dict[str, Any]) -> dict[str, Any]:
        label = str(data.get("label", "")).strip().lower().strip(".")
        tld = str(data.get("tld", "")).strip().lower().strip(".")
        err = dns.zone_error(label, tld)
        if err:
            raise UserError(err, field="domain")
        with self.lock:
            old = self.zone()
            new = f"{label}.{tld}"
            if new == old:
                return {"zone": old, "sync": self._last_sync}
            self.db.set_setting("domain_label", label)
            self.db.set_setting("domain_tld", tld)
            self.on_change(f"Domain changed to {new}", f"Every name moved from {old} to {new}.")
            self.write_dns()
            return {"zone": new, "sync": self.sync()}

    def set_tailnet_only(self, on: bool) -> dict[str, Any]:
        with self.lock:
            self.db.set_setting("tailnet_only", "1" if on else "0")
            self.on_change("Name access changed",
                           "Only Tailscale devices can open names." if on else "Any network that reaches the proxy can open names.")
            return self.sync()

    # --- discovery -----------------------------------------------------------------

    def targets(self) -> dict[str, Any]:
        server = self.server()
        errors: dict[str, str] = {}
        apps: list[dict[str, Any]] = []
        others: list[dict[str, Any]] = []
        listeners = ports.listening()
        reachable = {listener.port for listener in listeners if listener.wildcard or listener.ip == server.ip}
        local_only = {listener.port for listener in listeners if listener.loopback} - reachable
        try:
            containers = self.docker.containers()
        except DockerError as exc:
            containers = []
            errors["docker"] = str(exc)

        proxy = next((c for c in containers if c.name == self.cfg.npm_container), None)
        proxy_nets = set(proxy.networks) if proxy else set()
        skip = {53} | ({p for _, p, _ in proxy.published} if proxy else {80, 81, 443})
        claimed: set[int] = set()

        for c in containers:
            if c is proxy or c.name.startswith(OWN_CONTAINERS):
                continue
            opts: list[dict[str, Any]] = []
            shared = sorted(proxy_nets & set(c.networks)) if not c.host_network else []
            if shared:
                for p in sorted(c.exposed):
                    opts.append({"host": c.name, "port": p, "detail": f"port {p} on the {shared[0]} network"})
            seen_pub: set[int] = set()
            for ip, pub, _priv in c.published:
                if ip not in ("", "0.0.0.0", "::", server.ip) or pub in seen_pub:
                    continue
                seen_pub.add(pub)
                claimed.add(pub)
                if not shared:
                    opts.append({"host": server.ip, "port": pub, "detail": f"port {pub}"})
            if c.host_network:
                candidates: dict[int, str] = {}
                for var, p in sorted(c.env_ports.items(), key=lambda kv: (kv[0] != "PORT", kv[0])):
                    candidates.setdefault(p, var)
                for p in sorted(c.exposed):
                    candidates.setdefault(p, "EXPOSE")
                for p, why in candidates.items():
                    if p in reachable:
                        claimed.add(p)
                        opts.append({"host": server.ip, "port": p, "detail": f"port {p} ({why})"})
                    elif p in local_only:
                        opts.append({"host": server.ip, "port": p, "detail": f"port {p} ({why}), localhost only",
                                     "disabled": True})
            if not opts:
                opts.append({"host": "", "port": None, "detail": "no reachable port found", "disabled": True})
            for o in opts:
                apps.append({
                    "id": f"container:{c.name}:{o['port']}",
                    "source": f"container:{c.name}",
                    "name": c.name,
                    "label": f"{c.name} · {o['detail']}",
                    "state": c.state,
                    "disabled": False,
                    **o,
                })

        seen_other: set[int] = set()
        for listener in listeners:
            if listener.port in claimed or listener.port in skip or listener.port in seen_other or listener.loopback:
                continue
            if not (listener.wildcard or listener.ip == server.ip):
                continue
            if not listener.wildcard and listener.port >= 32768:
                continue  # tailscaled's own peer API and similar ephemeral listeners
            seen_other.add(listener.port)
            name = WELL_KNOWN.get(listener.port, f"Port {listener.port}")
            others.append({
                "id": f"port:{listener.port}",
                "source": f"port:{listener.port}",
                "name": name,
                "label": f"{name} · port {listener.port}" if listener.port in WELL_KNOWN else name,
                "host": server.ip,
                "port": listener.port,
                "detail": f"port {listener.port}",
                "disabled": False,
            })

        devices: list[dict[str, Any]] = []
        try:
            devices = [d.as_dict() for d in self.ts.devices()]
        except TailscaleError as exc:
            errors["tailscale"] = str(exc)

        return {
            "server": {"name": server.hostname, "ip": server.ip},
            "apps": apps,
            "ports": others,
            "devices": devices,
            "errors": errors,
        }

    # --- health ----------------------------------------------------------------------

    def reachability(self) -> dict[int, dict[str, Any]]:
        cached = self._reach
        if cached and time.monotonic() - cached[0] < REACHABILITY_TTL:
            return cached[1]
        rows = self.db.all("SELECT id, kind, target_host, target_port FROM records")
        try:
            by_name = {c.name: next(iter(c.networks.values()), "") for c in self.docker.containers()}
        except DockerError:
            by_name = {}
        try:
            online = {d.ip: d.online for d in self.ts.devices()}
        except TailscaleError:
            online = {}

        def probe(r: dict[str, Any]) -> tuple[int, dict[str, Any]]:
            if r["kind"] == "device":
                state = online.get(r["target_host"])
                if state is None:
                    return r["id"], {"ok": None, "why": "Not a device in your tailnet"}
                return r["id"], {"ok": state, "why": None if state else "Device is offline"}
            # Container names only resolve inside Docker networks; probe their IP instead.
            host = by_name.get(r["target_host"]) or r["target_host"]
            try:
                with socket.create_connection((host, r["target_port"]), timeout=1.5):
                    return r["id"], {"ok": True, "why": None}
            except OSError:
                return r["id"], {"ok": False, "why": f"Nothing answered on {r['target_host']}:{r['target_port']}"}

        if rows:
            with ThreadPoolExecutor(max_workers=8) as pool:
                result = dict(pool.map(probe, rows))
        else:
            result = {}
        self._reach = (time.monotonic(), result)
        return result

    def checks(self) -> list[dict[str, Any]]:
        server = self.server()
        zone = self.zone()
        bind = self.bind_ip()
        checks: list[dict[str, Any]] = []

        checks.append({
            "id": "tailscale",
            "title": "Tailscale",
            "ok": server.error is None,
            "detail": server.error or f"This server is {server.hostname} ({server.ip}).",
            "fix": None,
        })

        try:
            rcode, addrs = dns.query_a(bind, f"dns.{zone}") if bind else (-1, [])
            ok = rcode == 0 and server.ip in addrs
            detail = (f"Answering for *.{zone} on {bind}." if ok
                      else f"The DNS server on {bind or '?'} didn't answer correctly (code {rcode}). "
                           "Check the sheltie-dns container: docker logs sheltie-dns")
        except OSError as exc:
            ok, detail = False, f"The DNS server on {bind} isn't answering ({exc}). Check: docker logs sheltie-dns"
        checks.append({"id": "dns", "title": "DNS server", "ok": ok, "detail": detail, "fix": None})

        try:
            got = self.ts.split_dns_routes().get(zone)
            ok = bool(got) and bind in got
            if ok:
                detail = f"Your devices ask {bind} about {zone}."
            elif got:
                detail = f"{zone} is sent to {', '.join(got)}, not {bind}."
            else:
                detail = f"Your tailnet doesn't send {zone} lookups here yet."
        except TailscaleError as exc:
            ok, detail = False, str(exc)
        checks.append({
            "id": "split_dns",
            "title": "Tailscale split DNS",
            "ok": ok,
            "detail": detail,
            "fix": None if ok else {
                "steps": [
                    "Open the Tailscale admin console → DNS.",
                    "Under Nameservers, choose Add nameserver → Custom.",
                    f"Enter {bind}.",
                    f"Turn on “Restrict to domain” and enter {zone}.",
                    "Save. Devices pick it up within a minute.",
                ],
                "link": "https://login.tailscale.com/admin/dns",
                "copy": {"Nameserver": bind, "Domain": zone},
            },
        })

        npm_ok, npm_detail = False, ""
        if not self.npm.configured:
            npm_detail = "Not connected. Names resolve, but the browser can't open them without the proxy."
        else:
            try:
                me = self.npm.me()
                npm_ok = True
                npm_detail = f"Connected as {me.get('email')} (Nginx Proxy Manager {self.npm.version()})."
            except NpmError as exc:
                npm_detail = str(exc)
        checks.append({
            "id": "npm",
            "title": "Nginx Proxy Manager",
            "ok": npm_ok,
            "detail": npm_detail,
            "fix": None if npm_ok else {
                "steps": [
                    f"Open Nginx Proxy Manager (http://{server.ip}:81) → Users → Add user.",
                    "Name it Sheltie, with an email like sheltie@example.com. Don't make it an administrator.",
                    "Permissions: Item visibility “Created items only”; Proxy hosts and Access lists “Manage”; "
                    "everything else “Hidden”.",
                    "Set a password for it (no 2FA).",
                    "Put the email and password in Sheltie's .env as SHELTIE_NAMES_NPM_EMAIL and "
                    "SHELTIE_NAMES_NPM_PASSWORD, then run: docker compose up -d",
                ],
                "link": None,
                "copy": None,
            },
        })

        try:
            self.docker.containers()
            docker_ok, docker_detail = True, "Reading the container list."
        except DockerError as exc:
            docker_ok, docker_detail = False, str(exc)
        checks.append({"id": "docker", "title": "App discovery", "ok": docker_ok, "detail": docker_detail, "fix": None})
        return checks

    # --- import --------------------------------------------------------------------

    def import_names(self, path: str) -> dict[str, int]:
        """Copy names and settings from another names database. Only into an empty list, so nothing is overwritten."""
        if not os.path.isfile(path):
            raise UserError(f"No file at {path}.")
        with self.lock:
            if self.db.one("SELECT 1 FROM records"):
                raise UserError("Sheltie already has names. Import only works into an empty list.")
            src = sqlite3.connect(path)
            src.row_factory = sqlite3.Row
            try:
                settings = {row["key"]: row["value"] for row in src.execute("SELECT key, value FROM settings")}
                records = [dict(row) for row in src.execute("SELECT * FROM records")]
                garbage = [dict(row) for row in src.execute("SELECT npm_kind, npm_id FROM npm_garbage")]
            except sqlite3.DatabaseError as exc:
                raise UserError(f"That doesn't look like a names database ({exc}).") from None
            finally:
                src.close()

            for key in IMPORTED_SETTINGS:
                if key in settings:
                    self.db.set_setting(key, settings[key])
            imported = 0
            for r in records:
                if r["kind"] not in ("proxy", "device"):
                    # Only app and device names carry over. Anything else (such as a redirect for
                    # dns.<zone>) has its proxy host removed on the next sync.
                    if r.get("npm_id") is not None:
                        garbage.append({"npm_kind": r["npm_kind"], "npm_id": r["npm_id"]})
                    continue
                self.db.execute(
                    "INSERT INTO records (name, kind, target_host, target_port, scheme, websockets, source, label, "
                    "npm_kind, npm_id, created_at, updated_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (r["name"], r["kind"], r["target_host"], r["target_port"], r["scheme"], r["websockets"],
                     r["source"], r["label"], r["npm_kind"], r["npm_id"], r["created_at"], r["updated_at"],
                     r.get("created_by") or "import"),
                )
                imported += 1
            for g in garbage:
                self.db.execute("INSERT OR IGNORE INTO npm_garbage (npm_kind, npm_id) VALUES (?, ?)",
                                (g["npm_kind"], g["npm_id"]))
            self.on_change("Names imported", f"{imported} name(s) now managed by Sheltie under {self.zone()}.")
            self._reach = None
            self.write_dns()
            return {"names": imported, "cleanups": len(garbage)}


def build_names_service(config: dict[str, Any], on_change: Callable[[str, str], None] | None = None,
                        data_dir: str = "state") -> NamesService | None:
    """The names service, or None when names are turned off (the default)."""
    cfg = NamesConfig.from_config(config, data_dir)
    if not cfg.enabled:
        return None
    return NamesService(
        cfg,
        Database(cfg.db_path),
        Tailscale(cfg.tailscale_socket),
        Docker(),
        Npm(cfg.npm_url, cfg.npm_email, cfg.npm_password),
        on_change,
    )
