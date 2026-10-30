"""Listening TCP ports on this server, read from /proc (Sheltie uses host networking)."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass


@dataclass(frozen=True)
class Listener:
    ip: str
    port: int

    @property
    def wildcard(self) -> bool:
        return self.ip in ("0.0.0.0", "::")

    @property
    def loopback(self) -> bool:
        return ipaddress.ip_address(self.ip).is_loopback


def _decode(hex_addr: str) -> str:
    raw = bytes.fromhex(hex_addr)
    if len(raw) == 4:
        return str(ipaddress.IPv4Address(raw[::-1]))
    # IPv6 is four little-endian 32-bit words.
    words = b"".join(raw[i : i + 4][::-1] for i in range(0, 16, 4))
    addr = ipaddress.IPv6Address(words)
    return str(addr.ipv4_mapped) if addr.ipv4_mapped else str(addr)


def parse_proc_net(text: str) -> list[Listener]:
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4 or parts[3] != "0A":  # 0A = LISTEN
            continue
        addr, _, port = parts[1].partition(":")
        out.append(Listener(_decode(addr), int(port, 16)))
    return out


def listening(proc_root: str = "/proc") -> list[Listener]:
    found: set[Listener] = set()
    for name in ("tcp", "tcp6"):
        try:
            with open(f"{proc_root}/net/{name}") as fh:
                found.update(parse_proc_net(fh.read()))
        except OSError:
            continue
    return sorted(found, key=lambda listener: (listener.port, listener.ip))
