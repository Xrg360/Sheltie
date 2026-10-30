import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from typing import Any
from unittest.mock import patch

from monitors import token as token_command
from monitors.api import GENERATED_TOKEN_KEY, ApiServer, names_action
from monitors.state import StateStore
from monitors.names import NamesConfig, NamesService, UserError, build_names_service
from monitors.names import dns, ports
from monitors.names.db import Database
from monitors.names.discovery import Container, env_ports, parse_container
from monitors.names.npm import PATHS, NpmError
from monitors.names.tailscale import Device, Server, TailscaleError

SERVER_IP = "100.127.28.25"


def make_config(data_dir: str, **over: Any) -> NamesConfig:
    base: dict[str, Any] = dict(
        enabled=True, data_dir=data_dir, default_domain="home.internals", npm_url="http://npm",
        npm_email="sheltie@example.com", npm_password="x", npm_container="npm",
        tailscale_socket="/nonexistent", dns_bind="", server_ip="", coredns_dir="/dns",
    )
    base.update(over)
    return NamesConfig(**base)


class FakeTS:
    def __init__(self) -> None:
        self.routes: dict[str, list[str]] = {}
        self.down = False

    def server(self) -> Server:
        if self.down:
            raise TailscaleError("Can't reach tailscaled")
        return Server("pookie", "pookie.tail.ts.net", SERVER_IP, "me@example.com", True)

    def devices(self) -> list[Device]:
        return [
            Device("pookie", "pookie.tail.ts.net", SERVER_IP, "linux", True, True),
            Device("phone", "phone.tail.ts.net", "100.70.176.88", "android", True, False),
        ]

    def split_dns_routes(self) -> dict[str, list[str]]:
        return self.routes


class FakeDocker:
    def __init__(self, containers: list[Container]) -> None:
        self._c = containers

    def containers(self) -> list[Container]:
        return self._c


class FakeNpm:
    configured = True

    def __init__(self) -> None:
        self.items: dict[str, dict[int, dict[str, Any]]] = {"proxy": {}, "redirect": {}, "access": {}}
        self.next_id = 1
        self.calls: list[tuple[str, str]] = []
        self.fail_domains: set[str] = set()

    def _check(self, body: dict[str, Any]) -> None:
        for d in body.get("domain_names", []):
            if d in self.fail_domains:
                raise NpmError(f"{d} is already in use", 400)

    def request(self, method: str, path: str, body: Any = None) -> Any:
        kind = next(k for k, p in PATHS.items() if path.startswith(p))
        if method == "GET":
            return list(self.items[kind].values())
        return None

    def get(self, kind: str, item_id: int) -> dict[str, Any] | None:
        return self.items[kind].get(item_id)

    def create(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        self._check(body)
        self.calls.append(("create", kind))
        item = {**body, "id": self.next_id, "enabled": True}
        self.items[kind][self.next_id] = item
        self.next_id += 1
        return item

    def update(self, kind: str, item_id: int, body: dict[str, Any]) -> dict[str, Any]:
        self._check(body)
        self.calls.append(("update", kind))
        self.items[kind][item_id].update(body)
        return self.items[kind][item_id]

    def delete(self, kind: str, item_id: int) -> None:
        self.calls.append(("delete", kind))
        self.items[kind].pop(item_id, None)

    def me(self) -> dict[str, Any]:
        return {"email": "sheltie@example.com"}

    def version(self) -> str:
        return "2.15.1"


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_config(self.tmp.name)
        self.db = Database(self.cfg.db_path)
        self.npm = FakeNpm()
        self.ts = FakeTS()
        self.changes: list[tuple[str, str]] = []
        self.docker = FakeDocker([
            Container("npm", "jc21/npm", "running", "homelab", {"homelab": "172.18.0.4"}, [("0.0.0.0", 80, 80)], {80}),
            Container("uptime-kuma", "kuma", "running", "homelab", {"homelab": "172.18.0.5"}, [("0.0.0.0", 3001, 3001)], {3001}),
            Container("sheltie", "sheltie", "running", "host", {}, [], set(), {"PORT": 8710, "SHELTIE_API_PORT": 8711}),
            Container("sheltie-dns", "coredns", "running", "host", {}, [], set()),
            Container("hermes", "hermes", "running", "hermes_default", {"hermes_default": "172.19.0.2"}, [], set()),
        ])
        self.svc = NamesService(self.cfg, self.db, self.ts, self.docker, self.npm, lambda title, body: self.changes.append((title, body)))
        self.svc.write_dns()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def zone_text(self, zone: str = "home.internals") -> str:
        with open(os.path.join(self.cfg.dns_dir, f"{zone}.db")) as fh:
            return fh.read()


class DnsTests(unittest.TestCase):
    def test_labels(self) -> None:
        self.assertIsNone(dns.label_error("sheltie"))
        self.assertIsNone(dns.label_error("uptime-kuma2"))
        for bad in ("", "-x", "x-", "UPPER", "a.b", "a_b", "x" * 64):
            self.assertIsNotNone(dns.label_error(bad), bad)

    def test_zone(self) -> None:
        self.assertIsNone(dns.zone_error("home", "internals"))
        self.assertIsNone(dns.zone_error("lab.home", "internal"))
        self.assertIsNotNone(dns.zone_error("home", "123"))
        self.assertIsNotNone(dns.zone_error("ho me", "internal"))

    def test_render_zone_has_soa_ns_and_records(self) -> None:
        text = dns.render_zone("home.internals", [("sheltie", SERVER_IP), ("phone", "100.70.176.88")], 42, SERVER_IP)
        self.assertIn("$ORIGIN home.internals.", text)
        self.assertIn("SOA dns.home.internals. hostmaster.home.internals. 42 ", text)
        self.assertIn(f"dns 60 IN A {SERVER_IP}", text)
        self.assertIn("phone 60 IN A 100.70.176.88", text)
        self.assertIn("Generated by Sheltie", text)

    def test_write_coredns_replaces_old_zone_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            dns.write_coredns(d, "/dns", "home.internals", SERVER_IP, [], 1, SERVER_IP)
            dns.write_coredns(d, "/dns", "lab.internal", SERVER_IP, [], 2, SERVER_IP)
            self.assertEqual(sorted(os.listdir(d)), ["Corefile", "lab.internal.db"])
            with open(os.path.join(d, "Corefile")) as fh:
                core = fh.read()
            self.assertIn("lab.internal:53 {", core)
            self.assertIn(f"bind {SERVER_IP}", core)
            self.assertIn("file /dns/lab.internal.db", core)


class PortsAndDiscoveryTests(unittest.TestCase):
    def test_parse_proc_net(self) -> None:
        tcp = (
            "  sl  local_address rem_address   st\n"
            "   0: 00000000:21FE 00000000:0000 0A 00000000\n"   # 0.0.0.0:8702 LISTEN
            "   1: 0100007F:21FF 00000000:0000 0A 00000000\n"   # 127.0.0.1:8703 LISTEN
            "   2: 0100007F:1F90 0100007F:9C40 01 00000000\n"   # established, ignored
        )
        got = ports.parse_proc_net(tcp)
        self.assertEqual([(entry.ip, entry.port, entry.wildcard, entry.loopback) for entry in got],
                         [("0.0.0.0", 8702, True, False), ("127.0.0.1", 8703, False, True)])

    def test_parse_ipv6_wildcard(self) -> None:
        tcp6 = "header\n   0: 00000000000000000000000000000000:2206 00000000000000000000000000000000:0000 0A 0\n"
        (entry,) = ports.parse_proc_net(tcp6)
        self.assertEqual((entry.ip, entry.port, entry.wildcard), ("::", 8710, True))

    def test_env_ports_only_port_vars(self) -> None:
        env = ["PORT=8710", "SHELTIE_API_PORT=8711", "TOKEN=12345", "PORTAL=1", "BAD_PORT=99999", "X_PORT=abc"]
        self.assertEqual(env_ports(env), {"PORT": 8710, "SHELTIE_API_PORT": 8711})

    def test_parse_container_bridge_and_host(self) -> None:
        bridge = parse_container({
            "Names": ["/kuma"], "Image": "kuma", "State": "running", "HostConfig": {"NetworkMode": "homelab"},
            "NetworkSettings": {"Networks": {"homelab": {"IPAddress": "172.18.0.5"}}},
            "Ports": [{"PrivatePort": 3001, "PublicPort": 3001, "IP": "0.0.0.0", "Type": "tcp"},
                      {"PrivatePort": 53, "Type": "udp"}],
        })
        self.assertEqual((bridge.name, bridge.networks, bridge.exposed, bridge.published),
                         ("kuma", {"homelab": "172.18.0.5"}, {3001}, [("0.0.0.0", 3001, 3001)]))
        host = parse_container(
            {"Names": ["/sheltie"], "HostConfig": {"NetworkMode": "host"}, "Ports": []},
            {"Config": {"ExposedPorts": {"8710/tcp": {}}, "Env": ["PORT=8710", "SECRET=1"]}},
        )
        self.assertTrue(host.host_network)
        self.assertEqual((host.exposed, host.env_ports), ({8710}, {"PORT": 8710}))


class RecordTests(Base):
    def test_create_app_record_creates_proxy_with_acl(self) -> None:
        rec = self.svc.create_record({"name": "Sheltie", "mode": "app", "host": SERVER_IP, "port": 8710})
        self.assertEqual(rec["fqdn"], "sheltie.home.internals")
        self.assertIsNone(rec["sync_error"])
        (proxy,) = self.npm.items["proxy"].values()
        self.assertEqual((proxy["forward_host"], proxy["forward_port"]), (SERVER_IP, 8710))
        (acl,) = self.npm.items["access"].values()
        self.assertEqual(acl["name"], "Sheltie: Tailscale devices only")
        self.assertEqual(proxy["access_list_id"], acl["id"])
        self.assertIn(f"sheltie 60 IN A {SERVER_IP}", self.zone_text())

    def test_no_redirect_host_for_the_dns_name(self) -> None:
        # dns.<zone> is only an A record for the DNS server; no proxy or redirect host is made for it.
        self.svc.sync()
        self.assertEqual(self.npm.items["redirect"], {})
        self.assertEqual(self.svc.records(), [])
        self.assertIn(f"dns 60 IN A {SERVER_IP}", self.zone_text())

    def test_existing_access_list_is_reused_and_given_sheltie_name(self) -> None:
        self.npm.items["access"][7] = {"id": 7, "name": "Old app: Tailscale devices only"}
        self.db.set_setting("npm_acl_id", "7")
        self.svc.create_record({"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": 3001})
        self.assertEqual(list(self.npm.items["access"]), [7])
        self.assertEqual(self.npm.items["access"][7]["name"], "Sheltie: Tailscale devices only")
        (proxy,) = self.npm.items["proxy"].values()
        self.assertEqual(proxy["access_list_id"], 7)
        self.npm.calls.clear()
        self.svc.sync()
        self.assertEqual(self.npm.calls, [])

    def test_device_without_port_is_dns_only(self) -> None:
        self.svc.create_record({"name": "phone", "mode": "device", "host": "100.70.176.88"})
        self.assertEqual(self.npm.items["proxy"], {})
        self.assertIn("phone 60 IN A 100.70.176.88", self.zone_text())

    def test_switching_device_to_port_adds_then_removes_proxy(self) -> None:
        rec = self.svc.create_record({"name": "phone", "mode": "device", "host": "100.70.176.88"})
        self.svc.update_record({"id": rec["id"], "name": "phone", "mode": "device", "host": "100.70.176.88", "port": 8080})
        self.assertEqual(len(self.npm.items["proxy"]), 1)
        self.svc.update_record({"id": rec["id"], "name": "phone", "mode": "device", "host": "100.70.176.88"})
        self.assertEqual(self.npm.items["proxy"], {})

    def test_validation(self) -> None:
        cases = [
            ({"name": "dns", "mode": "app", "host": SERVER_IP, "port": 1}, "name"),
            ({"name": "x", "mode": "app", "host": SERVER_IP, "port": 70000}, "port"),
            ({"name": "x", "mode": "app", "host": SERVER_IP}, "port"),
            ({"name": "x", "mode": "app", "host": "bad host!", "port": 1}, "host"),
            ({"name": "x", "mode": "device", "host": "not-an-ip"}, "host"),
            ({"name": "x", "mode": "somewhere", "host": SERVER_IP}, "mode"),
            ({"name": "x", "mode": "app", "host": SERVER_IP, "port": 1, "scheme": "ftp"}, "scheme"),
        ]
        for data, field in cases:
            with self.subTest(data=data), self.assertRaises(UserError) as ctx:
                self.svc.create_record(data)
            self.assertEqual(ctx.exception.field, field)
        self.svc.create_record({"name": "x", "mode": "app", "host": "uptime-kuma", "port": 3001})
        with self.assertRaises(UserError) as ctx:
            self.svc.create_record({"name": "x", "mode": "app", "host": SERVER_IP, "port": 1})
        self.assertIn("already exists", str(ctx.exception))

    def test_update_and_delete_unknown_id(self) -> None:
        for bad in ({"id": 999, "name": "x", "mode": "device", "host": SERVER_IP}, {"id": "abc"}, {}):
            with self.subTest(bad=bad):
                with self.assertRaises(UserError):
                    self.svc.update_record(bad)
                with self.assertRaises(UserError):
                    self.svc.delete_record(bad)

    def test_delete_removes_proxy_host_and_record(self) -> None:
        rec = self.svc.create_record({"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": 3001})
        removed = self.svc.delete_record({"id": rec["id"]})
        self.assertEqual(removed["fqdn"], "kuma.home.internals")
        self.assertEqual(self.npm.items["proxy"], {})
        self.assertEqual(self.svc.records(), [])
        self.assertNotIn("kuma 60", self.zone_text())

    def test_npm_conflict_is_reported_on_the_record(self) -> None:
        self.npm.fail_domains.add("kuma.home.internals")
        rec = self.svc.create_record({"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": 3001})
        self.assertIn("already in use", rec["sync_error"])
        self.npm.fail_domains.clear()
        self.svc.sync()
        self.assertIsNone(self.svc._record(rec["id"])["sync_error"])

    def test_sync_adopts_lost_host_instead_of_duplicating(self) -> None:
        rec = self.svc.create_record({"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": 3001})
        self.db.execute("UPDATE records SET npm_id = NULL, npm_kind = NULL WHERE id = ?", (rec["id"],))
        self.svc.sync()
        self.assertEqual(len(self.npm.items["proxy"]), 1)

    def test_sync_is_idempotent(self) -> None:
        self.svc.create_record({"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": 3001})
        self.npm.calls.clear()
        self.svc.sync()
        self.assertEqual(self.npm.calls, [])

    def test_change_domain_moves_everything(self) -> None:
        self.svc.create_record({"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": 3001})
        self.svc.change_domain({"label": "Lab", "tld": "internal."})
        self.assertEqual(self.svc.zone(), "lab.internal")
        (proxy,) = self.npm.items["proxy"].values()
        self.assertEqual(proxy["domain_names"], ["kuma.lab.internal"])
        self.assertTrue(os.path.exists(os.path.join(self.cfg.dns_dir, "lab.internal.db")))
        self.assertFalse(os.path.exists(os.path.join(self.cfg.dns_dir, "home.internals.db")))
        with self.assertRaises(UserError):
            self.svc.change_domain({"label": "lab", "tld": "1"})

    def test_tailnet_only_off_clears_acl(self) -> None:
        self.svc.create_record({"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": 3001})
        self.svc.set_tailnet_only(False)
        (proxy,) = self.npm.items["proxy"].values()
        self.assertEqual(proxy["access_list_id"], 0)
        self.assertFalse(self.svc.state()["tailnet_only"])

    def test_without_npm_names_still_resolve(self) -> None:
        self.npm.configured = False
        rec = self.svc.create_record({"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": 3001})
        self.assertIn("isn't connected", rec["sync_error"])
        self.assertIn("kuma 60 IN A", self.zone_text())

    def test_changes_are_recorded(self) -> None:
        rec = self.svc.create_record({"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": 3001, "label": "Uptime Kuma"})
        self.svc.delete_record({"id": rec["id"]})
        self.assertEqual([title for title, _ in self.changes], ["Name added: kuma.home.internals", "Name removed: kuma.home.internals"])
        self.assertIn("Uptime Kuma (uptime-kuma:3001)", self.changes[0][1])

    def test_tailscale_down_keeps_last_known_address(self) -> None:
        self.svc.server()  # remembers the address
        self.ts.down = True
        server = self.svc.server()
        self.assertEqual(server.ip, SERVER_IP)
        self.assertIsNotNone(server.error)

    def test_state_payload(self) -> None:
        self.svc.create_record({"name": "phone", "mode": "device", "host": "100.70.176.88"})
        state = self.svc.state()
        self.assertTrue(state["enabled"])
        self.assertEqual(state["zone"], "home.internals")
        self.assertEqual(state["domain"], {"label": "home", "tld": "internals"})
        self.assertEqual(state["server"]["ip"], SERVER_IP)
        (rec,) = state["records"]
        self.assertEqual((rec["fqdn"], rec["points_to"], rec["url"]), ("phone.home.internals", "100.70.176.88", "http://phone.home.internals"))
        self.assertEqual(rec["reachable"], {"ok": True, "why": None})


class TargetTests(Base):
    def test_targets(self) -> None:
        listeners = [ports.Listener("0.0.0.0", 3001), ports.Listener("::", 8710), ports.Listener("127.0.0.1", 8711),
                     ports.Listener("0.0.0.0", 22), ports.Listener(SERVER_IP, 41641), ports.Listener("0.0.0.0", 80)]
        with patch.object(ports, "listening", lambda proc_root="/proc": listeners):
            t = self.svc.targets()
        by_id = {a["id"]: a for a in t["apps"]}
        # On the proxy's network: forward by container name.
        self.assertEqual((by_id["container:uptime-kuma:3001"]["host"], by_id["container:uptime-kuma:3001"]["port"]), ("uptime-kuma", 3001))
        # Host network: PORT var, reachable. Sheltie itself is a fine target.
        self.assertEqual(by_id["container:sheltie:8710"]["host"], SERVER_IP)
        self.assertFalse(by_id["container:sheltie:8710"]["disabled"])
        # Localhost-only port is shown but can't be picked.
        self.assertTrue(by_id["container:sheltie:8711"]["disabled"])
        # A container the proxy can't reach and with no published port.
        self.assertTrue(by_id["container:hermes:None"]["disabled"])
        # The proxy and the DNS sidecar are never offered.
        self.assertFalse([key for key in by_id if key.startswith(("container:npm:", "container:sheltie-dns:"))])
        self.assertEqual([p["port"] for p in t["ports"]], [22])
        self.assertEqual([d["name"] for d in t["devices"]], ["pookie", "phone"])

    def test_checks(self) -> None:
        self.ts.routes = {"home.internals": [SERVER_IP]}
        with patch.object(dns, "query_a", return_value=(0, [SERVER_IP])):
            checks = {c["id"]: c for c in self.svc.checks()}
        self.assertEqual(set(checks), {"tailscale", "dns", "split_dns", "npm", "docker"})
        self.assertTrue(all(c["ok"] for c in checks.values()))
        self.ts.routes = {}
        with patch.object(dns, "query_a", side_effect=OSError("timed out")):
            checks = {c["id"]: c for c in self.svc.checks()}
        self.assertFalse(checks["dns"]["ok"])
        self.assertIn("sheltie-dns", checks["dns"]["detail"])
        self.assertFalse(checks["split_dns"]["ok"])
        self.assertEqual(checks["split_dns"]["fix"]["copy"], {"Nameserver": SERVER_IP, "Domain": "home.internals"})


class ImportTests(Base):
    def make_import_db(self) -> str:
        path = os.path.join(self.tmp.name, "names-import.db")
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE records (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
                target_host TEXT NOT NULL DEFAULT '', target_port INTEGER, scheme TEXT NOT NULL DEFAULT 'http',
                websockets INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT '', label TEXT NOT NULL DEFAULT '',
                npm_kind TEXT, npm_id INTEGER, sync_error TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                created_by TEXT NOT NULL DEFAULT '');
            CREATE TABLE npm_garbage (npm_kind TEXT NOT NULL, npm_id INTEGER NOT NULL, PRIMARY KEY (npm_kind, npm_id));
            CREATE TABLE credentials (id TEXT PRIMARY KEY);
            INSERT INTO settings VALUES ('domain_label', 'lab'), ('domain_tld', 'internal'), ('npm_acl_id', '3'),
                ('tailnet_only', '1'), ('passkey_secret', 'not copied');
            INSERT INTO records (name, kind, label, npm_kind, npm_id, created_at, updated_at, created_by)
                VALUES ('dns', 'system', 'DNS redirect', 'redirect', 1, 1, 1, 'system');
            INSERT INTO records (name, kind, target_host, target_port, source, label, npm_kind, npm_id, created_at, updated_at, created_by)
                VALUES ('sheltie', 'proxy', '100.127.28.25', 8710, 'container:sheltie', 'sheltie', 'proxy', 2, 5, 6, 'me@example.com');
            INSERT INTO records (name, kind, target_host, created_at, updated_at) VALUES ('phone', 'device', '100.70.176.88', 7, 8);
        """)
        conn.commit()
        conn.close()
        return path

    def test_import_copies_names_settings_and_cleans_up_other_hosts(self) -> None:
        self.npm.items["redirect"][1] = {"id": 1, "domain_names": ["dns.lab.internal"]}
        self.npm.items["proxy"][2] = {"id": 2, "domain_names": ["sheltie.lab.internal"], "forward_scheme": "http",
                                      "forward_host": SERVER_IP, "forward_port": 8710, "access_list_id": 3,
                                      "allow_websocket_upgrade": True, "block_exploits": True, "enabled": True}
        self.npm.items["access"][3] = {"id": 3, "name": "Sheltie: Tailscale devices only"}
        result = self.svc.import_names(self.make_import_db())
        self.assertEqual(result, {"names": 2, "cleanups": 1})
        self.assertEqual(self.svc.zone(), "lab.internal")
        self.assertEqual(self.db.get_setting("passkey_secret"), "")
        self.assertEqual(sorted(r["name"] for r in self.svc.records()), ["phone", "sheltie"])
        self.assertIn("sheltie 60 IN A", self.zone_text("lab.internal"))
        self.npm.calls.clear()
        self.svc.sync()
        # The old dns redirect goes; the existing proxy host is kept as it is, not recreated.
        self.assertEqual(self.npm.calls, [("delete", "redirect")])
        self.assertEqual(list(self.npm.items["proxy"]), [2])
        self.assertEqual(self.changes[-1][0], "Names imported")

    def test_import_refuses_when_names_exist(self) -> None:
        self.svc.create_record({"name": "phone", "mode": "device", "host": "100.70.176.88"})
        with self.assertRaises(UserError):
            self.svc.import_names(self.make_import_db())

    def test_import_rejects_missing_or_wrong_file(self) -> None:
        with self.assertRaises(UserError):
            self.svc.import_names(os.path.join(self.tmp.name, "nope.db"))
        junk = os.path.join(self.tmp.name, "junk.db")
        with open(junk, "w") as fh:
            fh.write("not sqlite")
        with self.assertRaises(UserError):
            self.svc.import_names(junk)


class ConfigTests(unittest.TestCase):
    def test_off_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(build_names_service({}))
            self.assertIsNone(build_names_service({"names": {"enabled": "yes please"}}))

    def test_env_turns_on_and_overrides_config(self) -> None:
        env = {"SHELTIE_NAMES_ENABLED": "1", "SHELTIE_NAMES_NPM_EMAIL": "env@example.com", "SHELTIE_NAMES_DOMAIN": "Lab.Internal"}
        with patch.dict(os.environ, env, clear=True):
            cfg = NamesConfig.from_config({"names": {"enabled": False, "npm_email": "file@example.com", "npm_url": "http://npm:81/"}})
        self.assertTrue(cfg.enabled)
        self.assertEqual((cfg.npm_email, cfg.default_domain, cfg.npm_url), ("env@example.com", "lab.internal", "http://npm:81"))
        self.assertEqual((cfg.dns_dir, cfg.db_path), (os.path.join("state", "dns"), os.path.join("state", "names.db")))

    def test_sync_interval_has_a_floor(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(NamesConfig.from_config({"names": {"sync_seconds": 5}}).sync_seconds, 60)


class NamesActionTests(Base):
    def test_unknown_action_is_404(self) -> None:
        self.assertIsNone(names_action(self.svc, "explode", {}))
        self.assertIsNone(names_action(self.svc, "foo/add", {}))

    def test_names_off(self) -> None:
        result = names_action(None, "add", {"name": "x"})
        assert result is not None
        self.assertFalse(result["ok"])
        self.assertIn("SHELTIE_NAMES_ENABLED", result["error"])

    def test_add_update_remove(self) -> None:
        added = names_action(self.svc, "add", {"name": "kuma", "mode": "app", "host": "uptime-kuma", "port": "3001"})
        assert added is not None
        self.assertEqual((added["ok"], added["message"]), (True, "kuma.home.internals added"))
        record_id = added["record"]["id"]
        saved = names_action(self.svc, "update", {"id": record_id, "name": "uptime", "mode": "app", "host": "uptime-kuma", "port": 3001})
        assert saved is not None
        self.assertEqual(saved["message"], "uptime.home.internals saved")
        removed = names_action(self.svc, "remove", {"id": record_id})
        assert removed is not None
        self.assertEqual(removed["message"], "uptime.home.internals removed")

    def test_user_errors_carry_the_field(self) -> None:
        result = names_action(self.svc, "add", {"name": "", "mode": "app"})
        self.assertEqual(result, {"ok": False, "error": "Name can't be empty.", "field": "name"})

    def test_domain_access_and_sync(self) -> None:
        result = names_action(self.svc, "domain", {"label": "lab", "tld": "internal"})
        assert result is not None
        self.assertEqual(result["message"], "Names now end in .lab.internal")
        # Only a real boolean turns the restriction on; anything else means off.
        result = names_action(self.svc, "access", {"tailnet_only": "false"})
        assert result is not None
        self.assertFalse(self.svc.tailnet_only())
        result = names_action(self.svc, "sync", {})
        assert result is not None
        self.assertTrue(result["ok"])
        self.npm.configured = False
        result = names_action(self.svc, "sync", {})
        assert result is not None
        self.assertFalse(result["ok"])
        self.assertIn("isn't connected", result["error"])


class FakeStatusService:
    def __init__(self, state_path: str) -> None:
        self.state = StateStore(state_path)

    def status(self) -> dict[str, Any]:
        return {}

    health = network = docker = sites = power = status


class NamesApiTests(Base):
    """The names endpoints through the real HTTP server, behind the action token."""

    def setUp(self) -> None:
        super().setUp()
        self.start_server(self.svc)

    def start_server(self, names: Any) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.server = ApiServer({"api": {"host": "127.0.0.1", "port": 0}}, FakeStatusService(os.path.join(self.tmp.name, "state.json")), object(), names)
            self.server.start()
        assert self.server.server is not None
        host, port = self.server.server.server_address[:2]
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.stop()
        assert self.server.server is not None
        self.server.server.server_close()
        super().tearDown()

    def call(self, path: str, body: dict[str, Any] | None = None, token: str | None = None) -> tuple[int, dict[str, Any]]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET")
        if token:
            request.add_header("X-Sheltie-Action-Token", token)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def test_read_is_open_and_changes_need_the_token(self) -> None:
        status, state = self.call("/api/names")
        self.assertEqual((status, state["enabled"], state["records"]), (200, True, []))
        new = {"name": "phone", "mode": "device", "host": "100.70.176.88"}
        self.assertEqual(self.call("/api/actions/names/add", new)[0], 403)
        status, result = self.call("/api/actions/names/add", new, token=self.server.action_token)
        self.assertEqual((status, result["ok"]), (200, True))
        self.assertEqual(self.call("/api/names")[1]["records"][0]["fqdn"], "phone.home.internals")

    def test_bad_input_is_400_with_field(self) -> None:
        status, result = self.call("/api/actions/names/add", {"name": "dns", "mode": "device", "host": SERVER_IP}, token=self.server.action_token)
        self.assertEqual((status, result["field"]), (400, "name"))

    def test_unknown_names_action_is_404(self) -> None:
        request = urllib.request.Request(self.base + "/api/actions/names/explode", data=b"{}", method="POST")
        request.add_header("X-Sheltie-Action-Token", self.server.action_token)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 404)

    def test_names_off_reads_as_disabled(self) -> None:
        self.server.stop()
        assert self.server.server is not None
        self.server.server.server_close()
        self.start_server(None)
        self.assertEqual(self.call("/api/names"), (200, {"enabled": False}))
        status, result = self.call("/api/names/targets")
        self.assertFalse(result["enabled"])


class TokenCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.config = os.path.join(self.tmp.name, "config.yml")
        self.state = os.path.join(self.tmp.name, "state.json")
        patcher = patch.multiple(token_command, CONFIG_PATH=self.config, STATE_PATH=self.state)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_prints_generated_token_from_state(self) -> None:
        StateStore(self.state).set(GENERATED_TOKEN_KEY, "generated-123")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(token_command.current_token(), "generated-123")

    def test_configured_token_wins_in_the_same_order_as_the_api(self) -> None:
        StateStore(self.state).set(GENERATED_TOKEN_KEY, "generated-123")
        with open(self.config, "w") as fh:
            fh.write("actions:\n  token: from-config\n")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(token_command.current_token(), "from-config")
        with patch.dict(os.environ, {"SHELTIE_ACTION_TOKEN": "from-env"}, clear=True):
            self.assertEqual(token_command.current_token(), "from-env")

    def test_no_token_yet_exits_nonzero_and_creates_nothing(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("sys.stderr"):
            self.assertEqual(token_command.main(), 1)
        self.assertFalse(os.path.exists(self.state))


if __name__ == "__main__":
    unittest.main()
