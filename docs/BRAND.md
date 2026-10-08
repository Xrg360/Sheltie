# Brand: name, search and identity

This page records why the project is called **Sheltie**, how it should show up in search, and how the visual identity is put together. The binding design rules are in [DESIGN.md](../DESIGN.md).

## Why we renamed Meerkat

"Meerkat" was a friendly name, but a poor one to be found by:

- Search results for "meerkat" are dominated by the animal, the 2015 Meerkat livestreaming app, and the UK "Compare the Meerkat" advertising campaign.
- In software, the name is shared by several unrelated projects, so "meerkat monitoring" is also crowded.

## Why Sheltie

A **sheltie** (Shetland sheepdog) is a small herding dog known for being watchful: it notices everything, raises the alarm early, and brings strays back to the flock. That is the product in one picture:

- **Watches** your homelab quietly, all the time (monitoring).
- **Raises the alarm** only when something actually changes (quiet, state-change alerts).
- **Brings strays back** — restarts crashed containers and repairs network links it safely can (rescue).

It keeps the friendly, animal personality of the original name, is short, and is easy to spell from hearing it ("Sheltie restarted Jellyfin").

**Slogan:** The watchdog for your homelab.
**Hero line (unchanged):** Know what happened while you were offline.

### Availability check (2026-10-08)

Most single-word animal names are already taken in software (Kelpie, Collie, Tarsier, Okapi, Kakapo, Hachiko and Pangolin all have active packages or projects). Sheltie came out clean:

| Where | Result |
|---|---|
| PyPI, npm (`sheltie`) | Free |
| Docker Hub | 3 tiny repositories, no product |
| GitHub | Only small personal repositories (the largest has 9 stars) |
| `ghcr.io/xrg360/sheltie`, `github.com/xrg360/sheltie` | Free (under the existing account) |
| `sheltie.dev`, `sheltie.io` | Not resolving (likely unregistered; confirm with a registrar) |
| `sheltie.com`, `sheltie.app` | Registered by someone else |
| Software products named "Sheltie" (web search) | None found |

Confirm with USPTO/EUIPO (classes 9 and 42) before any paid marketing.

## Search (SEO) plan

The bare word "sheltie" belongs to the dog breed, just as "meerkat" belongs to the animal. We don't need to win that page; we need to win the searches people make when choosing a tool:

- `<title>`: "Sheltie — Self-hosted homelab monitoring and auto-repair for Docker".
- Metadata keywords include "homelab monitoring", "uptime kuma alternative", "docker monitoring", "auto-heal docker", and "sheltie homelab" / "sheltie monitoring".
- Keep the `/compare/*` pages (Sheltie vs Uptime Kuma, Beszel, …). Comparison pages are what people search for when choosing a tool.
- Say "Formerly Meerkat" on the website and README for at least one year, and keep "meerkat homelab monitor" in the keywords so old links and searches still land.
- Register `sheltie.dev` (or `.io`) and point it at the website; keep the old domain redirecting.

## Visual identity: Ink & Cream

- **Canvas:** warm cream (`#fffaf0`) with white cards and hairline grey borders. All neutrals are true greys, with no brown, sand or green tints.
- **Ink:** near-black (`#0a0a0a`) for text, primary buttons, focus and selected states. In dark mode the canvas is a neutral near-black (`#0c0c0d`) and the ink becomes cream.
- **Status:** green, amber and red are reserved for state, always with an icon and a word.
- **Brand palette:** lavender, peach, ochre and pink (plus ink and cream) for the logo and website feature cards only. No greens or teals, because green means "up".
- **Type:** Inter if installed, otherwise the system font; display weight 600 with tight tracking. No downloaded web fonts.
- **Logo:** an ink sheltie head with folded ear tips, a cream blaze and a cream collar, on an ochre rounded tile ("the sheltie mark").

The style draws on modern editorial SaaS sites (cream canvas, ink CTAs, saturated feature cards), adapted so that on the dashboard every hue still means status. It does not reuse any other company's logo, illustrations or mascots.

## Migrating from Meerkat

Existing installs keep working after upgrading:

| Old | New | Status |
|---|---|---|
| `MEERKAT_*` environment variables | `SHELTIE_*` | Old names still read as a fallback |
| `/api/meerkat/*` proxy path | `/api/sheltie/*` | Old path rewritten to the new one |
| `X-Meerkat-Action-Token` header | `X-Sheltie-Action-Token` | Both accepted |
| `meerkat_*` Prometheus metrics | `sheltie_*` | Both emitted; old names **deprecated**, removed in a future minor release |
| Browser preferences (`meerkat.*` keys) | `sheltie.*` | Old values read automatically |
| Container name `meerkat` | `sheltie` | Both protected from restart and ignored by auto-heal by default |
| `ghcr.io/xrg360/meerkat` | `ghcr.io/xrg360/sheltie` | Update your compose file |

To switch an existing compose setup: change the image to `ghcr.io/xrg360/sheltie:latest`, optionally rename the service and container to `sheltie`, and rename `MEERKAT_*` variables to `SHELTIE_*` when convenient. Update Grafana panels to the `sheltie_*` metric names before the deprecated ones are removed.
