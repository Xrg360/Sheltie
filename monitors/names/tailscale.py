"""Read-only client for the Tailscale LocalAPI (tailscaled's unix socket).

Only reads are used: listing devices and the DNS config. Nothing is changed.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any


class TailscaleError(Exception):
    pass


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("local-tailscaled.sock", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


@dataclass(frozen=True)
class Device:
    name: str
    dns_name: str
    ip: str
    os: str
    online: bool
    is_self: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dns_name": self.dns_name,
            "ip": self.ip,
            "os": self.os,
            "online": self.online,
            "is_self": self.is_self,
        }


@dataclass(frozen=True)
class Server:
    hostname: str
    dns_name: str  # e.g. pookie.tail7ff517.ts.net (no trailing dot)
    ip: str
    owner_login: str
    https_enabled: bool


def _ipv4(ips: list[str]) -> str:
    return next((ip for ip in ips if ":" not in ip), ips[0] if ips else "")


class Tailscale:
    def __init__(self, socket_path: str, cache_seconds: float = 15.0) -> None:
        self.socket_path = socket_path
        self.cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._status: tuple[float, dict[str, Any]] | None = None

    def _get(self, path: str) -> Any:
        conn = _UnixConnection(self.socket_path, timeout=3)
        try:
            conn.request("GET", path, headers={"Sec-Tailscale": "localapi"})
            resp = conn.getresponse()
            body = resp.read()
        except OSError as exc:
            raise TailscaleError(f"Can't reach tailscaled: {exc}") from exc
        finally:
            conn.close()
        if resp.status != 200:
            raise TailscaleError(f"tailscaled said {resp.status}: {body[:200].decode(errors='replace')}")
        return json.loads(body)

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._status and time.monotonic() - self._status[0] < self.cache_seconds:
                return self._status[1]
        data = self._get("/localapi/v0/status")
        with self._lock:
            self._status = (time.monotonic(), data)
        return data

    def server(self) -> Server:
        st = self.status()
        me = st.get("Self") or {}
        users = st.get("User") or {}
        owner = users.get(str(me.get("UserID")), {}).get("LoginName", "")
        return Server(
            hostname=me.get("HostName", ""),
            dns_name=(me.get("DNSName") or "").rstrip("."),
            ip=_ipv4(me.get("TailscaleIPs") or []),
            owner_login=owner.lower(),
            https_enabled=bool(st.get("CertDomains")),
        )

    def devices(self) -> list[Device]:
        st = self.status()
        out: list[Device] = []
        me = st.get("Self")
        peers = list((st.get("Peer") or {}).values())
        for node, is_self in [(me, True)] + [(p, False) for p in peers]:
            if not node:
                continue
            ip = _ipv4(node.get("TailscaleIPs") or [])
            if not ip:
                continue
            out.append(
                Device(
                    name=node.get("HostName") or ip,
                    dns_name=(node.get("DNSName") or "").rstrip("."),
                    ip=ip,
                    os=node.get("OS", ""),
                    online=bool(node.get("Online")) or is_self,
                    is_self=is_self,
                )
            )
        out.sort(key=lambda d: (not d.is_self, not d.online, d.name.lower()))
        return out

    def split_dns_routes(self) -> dict[str, list[str]]:
        """Split DNS routes pushed by the tailnet, e.g. {'home.internals': ['100.1.2.3']}."""
        cfg = self._get("/localapi/v0/dns-config")
        routes: dict[str, list[str]] = {}
        for domain, resolvers in (cfg.get("Routes") or {}).items():
            addrs = []
            for r in resolvers or []:
                addr = str(r.get("Addr", ""))
                # Addr may be "1.2.3.4", "1.2.3.4:53" or "[v6]:53".
                if addr.startswith("["):
                    addr = addr[1 : addr.find("]")]
                elif addr.count(":") == 1:
                    addr = addr.split(":")[0]
                addrs.append(addr)
            routes[domain.rstrip(".").lower()] = addrs
        return routes
