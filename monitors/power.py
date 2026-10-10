"""Power supply state and the BIOS "power on when AC is connected" setting.

Dell calls the setting "AC Power Recovery" (or "Wake on AC" on laptops): when mains power
comes back, the machine stays off, powers on, or returns to its last state. On a homelab
server you want "on", so a power cut does not leave it off until someone presses the button.

Sheltie reads and changes it through the kernel's dell-smbios WMI interface
(/dev/wmi/dell-smbios), which needs root and host devices: the container is privileged.
"""

import fcntl
import glob
import os
import struct
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


POWER_SUPPLY_DIR = Path("/sys/class/power_supply")
DMI_DIR = Path("/sys/class/dmi/id")
SMBIOS_DEVICE = Path("/dev/wmi/dell-smbios")
TOKEN_GLOB = "/sys/devices/platform/dell-smbios.*/tokens"

# SMBIOS tokens for "AC Power Recovery Mode" (libsmbios token list). A BIOS only lists
# the modes it offers; laptops usually have off and on but not last.
AC_RECOVERY_TOKENS = {"off": 0x00A1, "last": 0x00A2, "on": 0x00A3}

CLASS_TOKEN_READ = 0
CLASS_TOKEN_WRITE = 1
SELECT_TOKEN_STD = 0
# _IOWR('W', 0, struct dell_wmi_smbios_buffer) from <linux/wmi.h>; the packed struct is 52 bytes.
DELL_WMI_SMBIOS_CMD = (3 << 30) | (52 << 16) | (ord("W") << 8)
# u64 length, then struct calling_interface_buffer: u16 class, u16 select, u32 input[4], u32 output[4].
_HEADER = struct.Struct("<QHH4I4i")

# A token read enters system management mode. The dashboard polls often, and the
# setting only changes when someone changes it, so a few minutes of cache is plenty.
CACHE_SECONDS = 300

SMBIOS_ERRORS = {-1: "the BIOS rejected the request", -2: "the BIOS does not support this request", -3: "a BIOS password is set"}


class SmbiosError(RuntimeError):
    pass


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def power_supply() -> dict[str, Any]:
    """Mains adapter and battery state from /sys/class/power_supply."""
    ac_online: bool | None = None
    battery_percent: int | None = None
    battery_status: str | None = None
    try:
        supplies = sorted(POWER_SUPPLY_DIR.iterdir())
    except OSError:
        supplies = []
    for supply in supplies:
        kind = _read_text(supply / "type")
        if kind == "Mains":
            online = _read_text(supply / "online")
            if online is not None:
                ac_online = bool(ac_online) or online == "1"
        elif kind == "Battery" and battery_percent is None:
            capacity = _read_text(supply / "capacity")
            battery_percent = int(capacity) if capacity and capacity.isdigit() else None
            battery_status = _read_text(supply / "status")
    return {"ac_online": ac_online, "battery_percent": battery_percent, "battery_status": battery_status}


class DellSmbios:
    """Token reads and writes through the dell-smbios WMI character device."""

    def __init__(self, device: Path = SMBIOS_DEVICE, token_glob: str = TOKEN_GLOB) -> None:
        self.device = device
        self.token_glob = token_glob
        self.lock = threading.Lock()

    def available(self) -> bool:
        return self.device.exists() and bool(glob.glob(self.token_glob))

    def token(self, token_id: int) -> tuple[int, int] | None:
        """(location, value) for a token the BIOS offers, or None. Raises PermissionError without root."""
        for directory in glob.glob(self.token_glob):
            base = Path(directory) / f"{token_id:04x}"
            try:
                location = Path(f"{base}_location").read_text(encoding="ascii")
                value = Path(f"{base}_value").read_text(encoding="ascii")
            except FileNotFoundError:
                continue
            return int(location, 16), int(value, 16)
        return None

    def call(self, cmd_class: int, cmd_select: int, inputs: tuple[int, ...]) -> tuple[int, ...]:
        """Run one SMBIOS call and return output[0..3]. output[0] is the BIOS return code."""
        padded = (list(inputs) + [0, 0, 0, 0])[:4]
        with self.lock:
            with open(self.device, "rb", buffering=0) as handle:
                # Reading the device returns the buffer size the driver expects.
                size = struct.unpack("<Q", handle.read(8))[0]
            buffer = bytearray(max(size, _HEADER.size))
            _HEADER.pack_into(buffer, 0, len(buffer), cmd_class, cmd_select, *padded, 0, 0, 0, 0)
            fd = os.open(self.device, os.O_RDWR)
            try:
                fcntl.ioctl(fd, DELL_WMI_SMBIOS_CMD, buffer, True)
            finally:
                os.close(fd)
        return tuple(_HEADER.unpack_from(buffer)[7:])

    def token_active(self, token_id: int) -> bool:
        found = self.token(token_id)
        if found is None:
            raise SmbiosError(f"token {token_id:04x} is not offered by this BIOS")
        location, value = found
        output = self.call(CLASS_TOKEN_READ, SELECT_TOKEN_STD, (location,))
        if output[0] != 0:
            raise SmbiosError(SMBIOS_ERRORS.get(output[0], f"BIOS returned {output[0]}"))
        return (output[1] & 0xFFFFFFFF) == value

    def activate_token(self, token_id: int) -> None:
        found = self.token(token_id)
        if found is None:
            raise SmbiosError(f"token {token_id:04x} is not offered by this BIOS")
        location, value = found
        output = self.call(CLASS_TOKEN_WRITE, SELECT_TOKEN_STD, (location, value))
        if output[0] != 0:
            raise SmbiosError(SMBIOS_ERRORS.get(output[0], f"BIOS returned {output[0]}"))


class PowerService:
    def __init__(self, smbios: DellSmbios | None = None, dmi_dir: Path = DMI_DIR) -> None:
        self.smbios = smbios or DellSmbios()
        self.dmi_dir = dmi_dir
        self.lock = threading.Lock()
        self._cached: dict[str, Any] | None = None
        self._cached_at = 0.0

    def status(self, fresh: bool = False) -> dict[str, Any]:
        payload = {
            "vendor": _read_text(self.dmi_dir / "sys_vendor"),
            "model": _read_text(self.dmi_dir / "product_name"),
            **power_supply(),
            "ac_recovery": self.ac_recovery(fresh=fresh),
        }
        return payload

    def ac_recovery(self, fresh: bool = False) -> dict[str, Any]:
        with self.lock:
            if not fresh and self._cached is not None and time.monotonic() - self._cached_at < CACHE_SECONDS:
                return dict(self._cached)
            result = self._read_ac_recovery()
            self._cached = result
            self._cached_at = time.monotonic()
            return dict(result)

    def _read_ac_recovery(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "supported": False,
            "mode": None,
            "modes": [],
            "method": None,
            "reason": None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        vendor = (_read_text(self.dmi_dir / "sys_vendor") or "").lower()
        if "dell" not in vendor:
            result["reason"] = "Only Dell BIOS settings are supported so far"
            return result
        if not self.smbios.available():
            result["reason"] = "The dell-smbios WMI interface is not available (dell_smbios and dell_wmi kernel modules)"
            return result
        try:
            modes = [mode for mode, token_id in AC_RECOVERY_TOKENS.items() if self.smbios.token(token_id) is not None]
        except PermissionError:
            result["reason"] = "Sheltie needs root and host devices to read BIOS settings (run the container privileged)"
            return result
        if not modes:
            result["reason"] = "This BIOS does not offer AC power recovery"
            return result

        result.update(supported=True, modes=modes, method="dell-smbios")
        try:
            for mode in modes:
                if self.smbios.token_active(AC_RECOVERY_TOKENS[mode]):
                    result["mode"] = mode
                    break
        except (OSError, SmbiosError) as exc:
            result["reason"] = f"Could not read the BIOS setting: {exc}"
        return result

    def set_ac_recovery(self, mode: str) -> dict[str, Any]:
        mode = str(mode or "").strip().lower()
        if mode not in AC_RECOVERY_TOKENS:
            return {"ok": False, "error": "mode must be one of: on, off, last"}
        current = self.ac_recovery(fresh=True)
        if not current["supported"]:
            return {"ok": False, "error": current["reason"] or "AC power recovery is not supported on this machine"}
        if mode not in current["modes"]:
            return {"ok": False, "error": f"this BIOS offers: {', '.join(current['modes'])}"}
        if current["mode"] == mode:
            return {"ok": True, "message": f"Power on with AC is already {mode}", "ac_recovery": current}
        try:
            self.smbios.activate_token(AC_RECOVERY_TOKENS[mode])
        except (OSError, SmbiosError) as exc:
            return {"ok": False, "error": f"Could not change the BIOS setting: {exc}"}
        updated = self.ac_recovery(fresh=True)
        if updated["mode"] != mode:
            return {"ok": False, "error": "The BIOS accepted the change but still reports the old setting", "ac_recovery": updated}
        return {"ok": True, "message": f"Power on with AC set to {mode}", "ac_recovery": updated}
