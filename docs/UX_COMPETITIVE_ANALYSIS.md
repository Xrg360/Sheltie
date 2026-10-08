# UI/UX competitive analysis

How Labwarden's user experience compares with the tools homelab users already run, **what we lack**, and the design decisions that follow. This complements the feature comparison in [COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md). The design rules themselves live in [DESIGN.md](../DESIGN.md).

Observations about other projects are based on their public demos, documentation and community write-ups as of October 2026, and are kept deliberately general. UIs change often, so check each project for its current state.

## The question each tool answers

| Tool | The question its home screen answers | Typical first impression |
|---|---|---|
| Uptime Kuma 2.x | "Which of my monitors are up?" | Polished monitor list with heartbeat bars and a detail pane. Strong status pages, 90+ notification providers configured in the UI. |
| Beszel 0.19 | "How are my servers doing?" | Clean table of systems with resource meters, per-system history charts (1h to 1 week), ZFS pools, and an iOS companion app with home-screen widgets. |
| Maintenant | "Is my whole Docker host healthy?" | One binary: auto-discovered containers, endpoints, TLS certificates, image updates, exposed-port warnings and a status page. |
| Netdata | "What is every metric doing right now?" | Very rich, very dense chart wall aimed at experts. |
| Gatus | "Are my endpoints healthy?" | Minimal, read-only status list driven by YAML. |
| Dozzle | "What is this container printing?" | Live, searchable multi-container log viewer. |
| Dockge / Portainer | "What is running, and how do I change it?" | Compose stacks and containers with start/stop/update controls and logs. |
| Pulse | "How is my Proxmox cluster?" | Unified view of Proxmox VMs, backups, Docker and Kubernetes with threshold alerts. |
| Homepage / Homarr | "Where are my services?" | Start pages with tiles and widgets; Homarr leads on drag-and-drop approachability. |
| **Labwarden** | **"Is everything OK, what happened while I was away, and what should I do?"** | One sentence, the problems with buttons to fix them, then the story since your last visit. |

## Dimension by dimension

| UX dimension | Uptime Kuma | Beszel | Maintenant | Dozzle / Dockge | **Labwarden today** |
|---|---|---|---|---|---|
| 3-second "am I OK?" | Scan the list for red | Scan the table | Dashboard summary | n/a | **Plain-language status sentence and glyph on every page** |
| "What happened while I was away?" | Per-monitor event history | Limited | Event list | — | **"Since your last visit" summary on Overview** |
| Next step for a problem | Mostly informational | Informational | Informational | Start/stop/restart, logs | **Every problem carries buttons** (but no logs yet) |
| Diagnosis (logs) | — | — | — | ✅ core feature | ❌ missing |
| Incident lifecycle | Per-monitor timeline, maintenance | Alert history | Alerts | — | Flat event list, no grouping or acknowledge |
| Correlated root cause | — | — | — | — | ❌ duplicates (site down + its container stopped) |
| History ranges | 24h / 30d uptime | 1h → 1w charts | Yes | — | Last 80 checks; host trend only "since you opened" |
| Check types | 20+ (HTTP, TCP, DNS, ping, push…) | n/a | HTTP, TCP, heartbeat, TLS | n/a | HTTP only |
| Notification setup | 90+ providers in the UI with "Test" | Webhooks/email in UI | In UI | — | Telegram via config only |
| First-run onboarding | Create admin, then empty list | Copy-paste agent command | Zero-config auto-discovery | Zero-config | Checklist, but the token comes from `docker logs` |
| Mobile | Usable, desktop-first | Responsive + iOS app | Responsive | Responsive | **Mobile-first: bottom tabs, sheets, 44px targets** (no push yet) |
| Keyboard / power use | Limited | Some search | Some | Search | **⌘K palette, `g`-shortcuts, `?` help** |
| Stale / offline honesty | Reconnect indicator | — | — | — | **Banner + last-known snapshot with its age** |
| Destructive actions | Confirms deletes | — | — | Confirms | **Confirms every restart/remove/clear; Undo on remove** |
| Accessibility | Color-coded bars | Partial | Partial | Partial | **WCAG 2.2 AA enforced by axe in CI; status never color-only** |
| Visual identity | Green accent, dark default | Neutral component-library look | Neutral dashboard | Utility | **Ink & Cream: cream canvas, ink actions, color only for status, warden mark** |
| Two-way control from phone | Notifications only | Notifications + app | Notifications | — | **Telegram commands plus a phone-ready dashboard** |

## What we lack

Labwarden is a monitoring **and rescue** tool. The gaps below are ranked by how much they weaken the rescue loop: notice → understand → fix → confirm it's fixed. Each one is tracked in [ROADMAP.md](ROADMAP.md#web-ui--ux-gaps).

### P0: gaps in the rescue loop (the core promise)

1. **Correlated problems.** Today "Blog is down" and "blog has stopped" appear as two separate problems with two different buttons. They are one incident: *"Blog is down because its container stopped"*, with a single **Start** action. No competitor does root-cause grouping for homelabs, so this becomes part of the moat. (`src/lib/insights.ts`)
2. **Technical copy leaks through.** "502 Server Error: Bad Gateway for url: https://…" and key-value event details ("Site: Blog · URL: … · Expected: 200 · Status: 502") break our own voice rules. Rewrite as "Returned 502 Bad Gateway" and "Blog went down: it answered 502 instead of 200". (`insights.ts`, `format.ts`)
3. **No logs in the rescue flow.** Dozzle, Portainer and Dockge all show logs. Without them, "Start" is a guess. Add **View logs** (last 200 lines, search, copy, follow) as a sheet on every container and on container problems. Needs a `/api/docker/logs` endpoint.
4. **Flat incident list.** Group events into incidents with start, end, duration, what auto-heal tried, and an **Acknowledge** action that stops repeat notifications. Model: Kuma's per-monitor timeline plus PagerDuty-style acknowledgement.
5. **First-run friction.** Users must run `docker logs … | grep token` before they can fix anything. Kuma and Homarr set up in the browser. Add a first-run claim screen (a one-time setup code), then a session login (roadmap Phase 3).
6. **Notification setup lives in config files.** Kuma configures 90+ providers in the UI with a **Send test** button. Add a "Where should alerts go?" section in Settings with a test button, backed by the planned Apprise bridge.

### P1: expected baseline

7. **History ranges** (1h, 24h, 7d, 30d) for host metrics and uptime percentages. Beszel and Kuma have them.
8. **More check types in the Add-monitor sheet:** TCP port, ping, DNS, **TLS certificate expiry**, and **heartbeat/cron push** URLs (Kuma, Gatus, Maintenant). Keep the "paste one thing, fold the rest" form.
9. **Per-container CPU/memory** and **"image update available"** (Beszel, Maintenant, WUD/Diun).
10. **Maintenance windows** and **per-monitor / per-container silence**. Today silence is global only.
11. **Installable PWA with web push.** We claim phone-first but rely on Telegram for push; Beszel ships an iOS app.
12. **Read-only shareable status page** so family can answer "is Jellyfin down?" themselves (Kuma, Gatus, Maintenant).

### P2: differentiators and polish

13. **Auto-heal policy UI:** opt in per container, attempts and backoff, a "gave up after 5 tries" state with escalation.
14. **Visual network root-cause chain** (this server → gateway → DNS → ISP) once the WAN dependency checks land.
15. **Compact density toggle** for Sam; incident CSV export and a shareable outage report.
16. **Multi-host switcher** (Phase 4) and **i18n** (strings are already centralized).

### UX fixes seen in the current screens

- Container names are used as headlines in lowercase ("blog has stopped"). Use "Container *blog* has stopped" with the name in code style, or the monitor's display name when correlated.
- "Since your last visit" repeats items already shown in "Needs attention". Group per item and dim what is already listed above.
- The host sparkline under "Vital signs" has no label or range.
- On mobile, problem action buttons are indented under the icon column; they should span the card width.

## What we take, and what we avoid

**Take**
- Uptime Kuma's heartbeat bars: instantly readable history. Labwarden mutes the healthy bars so failures pop.
- Beszel's restraint: clean tables, few colors, data first.
- Dozzle's logs-next-to-the-problem: diagnosis belongs in the rescue flow.
- Homarr's approachability: visual setup, no YAML needed for common tasks.
- Status-page clarity from Gatus and Kuma: one glance, one answer.
- Editorial SaaS polish for the website (cream canvas, ink CTAs, saturated feature cards), kept off the dashboard where hue means status.

**Avoid**
- Chart walls that require expertise to read (Netdata's strength for experts, a weakness for our primary persona).
- Long forms up front. Ask for the one thing that matters (the URL) and fold the rest.
- Color as decoration. When everything is green and blue, red stops meaning something.
- Silent staleness. A dashboard that shows old data as live is worse than no dashboard.

## Labwarden's UX moat

1. **Narrative over metrics.** The Overview reads like a short report: what's wrong, what happened, how the vitals look.
2. **Actionable by default.** Problems come with the button that fixes them, gated by confirmation and the action token.
3. **Outage honesty.** The UI is designed for the moments the network or server is unhealthy, which is exactly when other dashboards go blank.
4. **Phone-first.** Most checks happen away from the desk.
5. **A written design contract.** DESIGN.md, CODEOWNERS and CI checks keep the experience consistent as contributors join.

Closing the P0 gaps turns the moat from "tells you what's wrong" into "gets you from alert to fixed without leaving the page".

## Sources

- [Uptime Kuma 2.0 release coverage (AlternativeTo)](https://alternativeto.net/news/2025/10/uptime-kuma-2-0-introduces-mariadb-support-rootless-docker-modern-ui-and-upgrade-tools)
- [Beszel on GitHub](https://github.com/henrygd/beszel)
- [Beszel Companion v26.9.1 release notes](https://newreleases.io/project/github/Loriage/Beszel-Swift-App/release/v26.9.1)
- [Maintenant: containers, endpoints and certificates without tool sprawl (IT-Connect)](https://www.it-connect.tech/now-monitor-containers-endpoints-and-certificates-without-tool-sprawl/)
- [Maintenant on AlternativeTo](https://alternativeto.net/software/maintenant/about)
- [Dozzle real-time Docker log viewer (Linuxiac)](https://linuxiac.com/dozzle-real-time-docker-logs-viewer/)
- [Beszel vs Netdata vs Glances 2026 (TechFuel)](https://techfuelhq.com/homelab/beszel-vs-netdata-vs-glances-2026/)
- [Homepage vs Homarr](https://jisaku.com/posts/homepage-vs-homarr-dashboard)
- [Uptime Kuma vs Gatus (Bitdoze)](https://www.bitdoze.com/uptime-kuma-vs-gatus/)
- [Best self-hosted monitoring tools 2026 (selfhosting.sh)](https://selfhosting.sh/best/monitoring/)
