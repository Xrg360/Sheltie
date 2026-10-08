# Competitive analysis

This page compares Sheltie with the tools homelab users already run, and explains where Sheltie fits. The figures are approximate as of October 2026. Check each project for current details.

## Landscape

| Tool | What it is best at | Model |
|---|---|---|
| [Uptime Kuma](https://github.com/louislam/uptime-kuma) | Endpoint uptime checks, public status pages, 90+ notification providers. Version 2.x added MariaDB, rootless Docker and Globalping probes. ~80k★ | Single instance, configured in the UI |
| [Beszel](https://github.com/henrygd/beszel) | Lightweight host and container metrics with alerts | Hub (PocketBase) and outbound-only agents |
| [Gatus](https://github.com/TwiN/gatus) | Endpoint checks defined in YAML (status, latency, certificates, body conditions) | Single binary, config-as-code |
| [Netdata](https://github.com/netdata/netdata) | Per-second metrics and deep diagnostics | Agent, with Cloud or a parent node for multi-host |
| [healthchecks.io](https://healthchecks.io) | Dead man's switch: alerts when a ping *stops* arriving | Hosted or self-hosted |
| [docker-autoheal](https://github.com/willfarrell/docker-autoheal) | Restarts containers whose healthcheck reports `unhealthy` | Sidecar container |
| Prometheus + Alertmanager + node_exporter + cAdvisor | Everything, if you assemble and maintain it yourself | Many components |

## Feature comparison

| Capability | Uptime Kuma | Beszel | Gatus | Netdata | healthchecks.io | docker-autoheal | **Sheltie** |
|---|---|---|---|---|---|---|---|
| HTTP, TCP, DNS and ping endpoint checks | ✅ many types | ❌ | ✅ | partial | ❌ | ❌ | HTTP today, more planned |
| Host metrics (CPU, RAM, disk, temperature) | ❌ | ✅ | ❌ | ✅✅ | ❌ | ❌ | ✅ |
| Docker lifecycle **events** | basic | stats | ❌ | ✅ | ❌ | ❌ | ✅ |
| Auto-heal (containers and NICs) | ❌ | ❌ | ❌ | ❌ | ❌ | unhealthy only | ✅ intent-aware |
| NIC, default-route and WAN failover awareness | ❌ | ❌ | ❌ | partial | ❌ | ❌ | ✅ |
| Two-way chat-ops (bot commands) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ Telegram |
| Notification channels | 90+ | many (webhooks) | ~30 | many | many | ❌ | Telegram today, 100+ via Apprise planned |
| Offline outbox and "while you were away" digest | ❌ | ❌ | ❌ | ❌ | n/a | ❌ | planned (Phase 1) |
| Power-cut, crash and downtime forensics on boot | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | planned (Phase 1) |
| Off-site dead man's switch for the agent itself | DIY push monitor | hub notices agent down | ❌ | Cloud | ✅ core feature | ❌ | planned (Sentinel and peer mesh) |
| UPS (NUT) awareness | ❌ | ❌ | ❌ | ✅ collector | ❌ | ❌ | planned |
| Public status page | ✅✅ | ❌ | ✅ | ❌ | ❌ | ❌ | planned (Phase 3) |
| Multi-host | ❌ | ✅ | ❌ | Cloud or parent | n/a | ❌ | planned (Phase 4) |
| Prometheus `/metrics` | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ |

## Where Sheltie wins

Each competitor answers one question well:

- **Uptime Kuma:** "Is my website up?"
- **Beszel and Netdata:** "How are my servers doing?"
- **healthchecks.io:** "Did my job or host stop checking in?"

**Sheltie answers: "Something broke at home while I was away. What happened, did it fix itself, and what do I need to do?"**

No other tool combines these:

1. **Outage-awareness.** Alerts survive the outage that caused them, and you get one clear digest when connectivity returns.
2. **Downtime forensics.** On boot, Sheltie says whether the host crashed, was rebooted, or lost power, and for how long.
3. **Intent-aware self-healing.** Crashed containers and NICs that have a link but no address get repaired, but a `docker stop` or an unplugged cable is left alone.
4. **Network-path awareness.** Ethernet/Wi-Fi failover, default-route changes, and (planned) gateway vs. DNS vs. ISP root cause.
5. **Chat-ops.** You can check status and run repairs from your phone, with protection against stale commands.

## Where Sheltie should not compete

- **Public status pages and dozens of probe types.** Uptime Kuma owns this. Sheltie should push heartbeats *to* Uptime Kuma rather than replace it.
- **Per-second metric dashboards.** Netdata and Prometheus/Grafana own this. Sheltie exposes `/metrics` so it can sit next to them.
- **Large fleets.** Beszel and Prometheus scale further. Sheltie's hub mode is aimed at a handful of sites (home, office, VPS).

## Integration strategy

| Integrate with | How |
|---|---|
| Uptime Kuma, healthchecks.io | `heartbeat.urls` push pings (Phase 1) |
| Prometheus and Grafana | `/metrics` today, plus a dashboard JSON (good first issue) |
| Home Assistant | MQTT discovery and an add-on (good first issue) |
| NUT | UPS monitor (Phase 2) |
| Apprise | Notifier bridge for 100+ services (Phase 2) |

## Sources

- [Uptime Kuma 2.0 release coverage (AlternativeTo)](https://alternativeto.net/news/2025/10/uptime-kuma-2-0-introduces-mariadb-support-rootless-docker-modern-ui-and-upgrade-tools)
- [Uptime Kuma 2.1 coverage (Linuxiac)](https://linuxiac.com/uptime-kuma-2-1-monitoring-tool-adds-globalping-support/)
- [Beszel on GitHub](https://github.com/henrygd/beszel)
- [Uptime Kuma vs Gatus (Bitdoze)](https://www.bitdoze.com/uptime-kuma-vs-gatus/)
- [Best self-hosted monitoring tools 2026 (selfhosting.sh)](https://selfhosting.sh/best/monitoring/)
- [healthchecks.io FAQ](https://healthchecks.io/faq)
- [Apprise on PyPI](https://pypi.org/project/apprise)
