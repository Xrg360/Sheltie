# UI/UX competitive analysis

How Meerkat's user experience compares with the tools homelab users already run, and the design decisions that follow. This complements the feature comparison in [COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md). The design rules themselves live in [DESIGN.md](../DESIGN.md).

Observations about other projects are based on their public demos, documentation and community write-ups as of October 2026, and are kept deliberately general. UIs change often, so check each project for its current state.

## The question each tool answers

| Tool | The question its home screen answers | Typical first impression |
|---|---|---|
| Uptime Kuma | "Which of my monitors are up?" | Polished monitor list with heartbeat bars and a detail pane. Strong status pages. |
| Beszel | "How are my servers doing?" | Clean table of systems with resource meters; per-system charts. |
| Netdata | "What is every metric doing right now?" | Very rich, very dense chart wall aimed at experts. |
| Gatus | "Are my endpoints healthy?" | Minimal, read-only status list driven by YAML. |
| Homepage / Homarr / Dashy | "Where are my services?" | Start pages with tiles and widgets; Homarr leads on drag-and-drop approachability. |
| **Meerkat** | **"Is everything OK, what happened while I was away, and what should I do?"** | One sentence, the problems with buttons to fix them, then the story since your last visit. |

## Dimension by dimension

| UX dimension | Uptime Kuma | Beszel | Netdata | Gatus | Homepage / Homarr | **Meerkat** |
|---|---|---|---|---|---|---|
| 3-second "am I OK?" | Scan the list for red | Scan the table | Hard; needs expertise | Scan the list | Scan tiles | **Plain-language status sentence and glyph on every page** |
| "What happened while I was away?" | Per-monitor event history | Limited | Alert log | — | — | **"Since your last visit" summary on Overview** |
| Next step for a problem | Mostly informational | Informational | Some alert guidance | Informational | Links to services | **Every problem carries buttons: Start, View monitor, Open site, View network** |
| First-run onboarding | Create admin, then an empty list | Copy-paste agent command | Auto-discovery | Write config | Homarr: visual editor | **Setup checklist with progress (monitor, Telegram, token, notifications)** |
| Adding a website check | Form with many options up front | n/a | n/a | Edit YAML | Varies | **Paste a URL; name suggested; advanced options folded** |
| Mobile | Usable, desktop-first layout | Responsive | Heavy on phones | Fine (read-only) | Varies by tool | **Mobile-first: bottom tabs, bottom sheets, 44px targets** |
| Keyboard / power use | Limited | Some search | Some | — | Homarr has search | **⌘K command palette, `g`-shortcuts, `?` help** |
| Stale / offline honesty | Reconnect indicator | — | — | — | — | **Connection banner + last-known snapshot with its age** |
| Destructive actions | Confirms deletes | — | — | n/a | n/a | **Confirms every restart/remove/clear; Undo on remove** |
| Accessibility | Color-coded bars | Partial | Dense | Simple | Varies | **WCAG 2.2 AA enforced by axe in CI; status never color-only** |
| Visual identity | Green accent, dark default | Neutral component-library look | Busy | Minimal | Highly themeable | **Savanna: warm neutrals, color only for status, meerkat lookout mark** |
| Two-way control from phone | Notifications only | Notifications | Notifications | Notifications | — | **Telegram commands plus a phone-ready dashboard** |

## What we take, and what we avoid

**Take**
- Uptime Kuma's heartbeat bars: instantly readable history. Meerkat mutes the healthy bars so failures pop.
- Beszel's restraint: clean tables, few colors, data first.
- Homarr's approachability: visual setup, no YAML needed for common tasks.
- Status-page clarity from Gatus and Kuma: one glance, one answer.

**Avoid**
- Chart walls that require expertise to read (Netdata's strength for experts, a weakness for our primary persona).
- Long forms up front. Ask for the one thing that matters (the URL) and fold the rest.
- Color as decoration. When everything is green and blue, red stops meaning something.
- Silent staleness. A dashboard that shows old data as live is worse than no dashboard.

## Meerkat's UX moat

1. **Narrative over metrics.** The Overview reads like a short report: what's wrong, what happened, how the vitals look.
2. **Actionable by default.** Problems come with the button that fixes them, gated by confirmation and the action token.
3. **Outage honesty.** The UI is designed for the moments the network or server is unhealthy, which is exactly when other dashboards go blank.
4. **Phone-first.** Most checks happen away from the desk.
5. **A written design contract.** DESIGN.md, CODEOWNERS and CI checks keep the experience consistent as contributors join.

## Sources

- [Uptime Kuma 2.0 release coverage (AlternativeTo)](https://alternativeto.net/news/2025/10/uptime-kuma-2-0-introduces-mariadb-support-rootless-docker-modern-ui-and-upgrade-tools)
- [Beszel on GitHub](https://github.com/henrygd/beszel)
- [Uptime Kuma vs Gatus (Bitdoze)](https://www.bitdoze.com/uptime-kuma-vs-gatus/)
- [Best self-hosted monitoring tools 2026 (selfhosting.sh)](https://selfhosting.sh/best/monitoring/)
- [Self-hosted homepage dashboards: Homepage, Dashy, Homarr (pistack)](https://www.pistack.xyz/posts/self-hosted-homepage-dashboards-homepage-dashy-homarr-guide/)
- [Uptime Kuma overview (dreamserver.ro)](https://dreamserver.ro/en/blog/uptime-kuma-uptime-monitoring/)
