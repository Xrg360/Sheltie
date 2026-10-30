"""Which containers could a name point at, and on which ports."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

_PORT_VAR = re.compile(r"(^|_)PORT$")


class DockerError(Exception):
    pass


@dataclass
class Container:
    name: str
    image: str
    state: str
    network_mode: str
    networks: dict[str, str] = field(default_factory=dict)  # network name -> container IP
    published: list[tuple[str, int, int]] = field(default_factory=list)  # (host ip, host port, container port)
    exposed: set[int] = field(default_factory=set)
    env_ports: dict[str, int] = field(default_factory=dict)  # only for host-network containers

    @property
    def host_network(self) -> bool:
        return self.network_mode == "host"


def env_ports(env: list[str]) -> dict[str, int]:
    """Pick variables like PORT=8710 or APP_PORT=3000 out of a container's env.

    Only the variable names and numeric values are kept; nothing else from the
    environment is read or stored.
    """
    found: dict[str, int] = {}
    for item in env or []:
        key, _, value = item.partition("=")
        if _PORT_VAR.search(key.upper()) and value.isdigit() and 0 < int(value) < 65536:
            found[key] = int(value)
    return found


def parse_container(raw: dict[str, Any], detail: dict[str, Any] | None = None) -> Container:
    """Build a Container from Docker's /containers/json entry (plus /containers/<id>/json for host-network ones)."""
    nets = (raw.get("NetworkSettings") or {}).get("Networks") or {}
    c = Container(
        name=(raw.get("Names") or ["?"])[0].lstrip("/"),
        image=raw.get("Image", ""),
        state=raw.get("State", ""),
        network_mode=(raw.get("HostConfig") or {}).get("NetworkMode", ""),
        networks={k: (v or {}).get("IPAddress", "") for k, v in nets.items()},
    )
    for p in raw.get("Ports") or []:
        if p.get("Type") != "tcp":
            continue
        c.exposed.add(int(p["PrivatePort"]))
        if p.get("PublicPort"):
            c.published.append((p.get("IP", ""), int(p["PublicPort"]), int(p["PrivatePort"])))
    if c.host_network and detail:
        # Host-network containers report no ports; look at the image's
        # EXPOSE list and PORT-style variables instead.
        cfg = detail.get("Config") or {}
        for key in cfg.get("ExposedPorts") or {}:
            port, _, proto = key.partition("/")
            if proto == "tcp" and port.isdigit():
                c.exposed.add(int(port))
        c.env_ports = env_ports(cfg.get("Env") or [])
    return c


class Docker:
    """Lists containers through Sheltie's own Docker connection. Read-only calls only."""

    def __init__(self, cache_seconds: float = 10.0) -> None:
        self.cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._cache: tuple[float, list[Container]] | None = None

    def containers(self) -> list[Container]:
        with self._lock:
            if self._cache and time.monotonic() - self._cache[0] < self.cache_seconds:
                return self._cache[1]
        try:
            import docker

            api = docker.from_env().api
            out = []
            for raw in api.containers():
                is_host = (raw.get("HostConfig") or {}).get("NetworkMode") == "host"
                out.append(parse_container(raw, api.inspect_container(raw["Id"]) if is_host else None))
        except Exception as exc:
            raise DockerError(f"Can't reach Docker ({exc})") from exc
        out.sort(key=lambda c: c.name.lower())
        with self._lock:
            self._cache = (time.monotonic(), out)
        return out
