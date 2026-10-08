# Brand: name, search and identity

This page records why the project is called **Labwarden**, how it should show up in search, and how the visual identity is put together. The binding design rules are in [DESIGN.md](../DESIGN.md).

## Why we renamed Meerkat

"Meerkat" was a friendly name, but a poor one to be found by:

- Search results for "meerkat" are dominated by the animal, the 2015 Meerkat livestreaming app, and the UK "Compare the Meerkat" advertising campaign. A homelab tool could not win that results page.
- The word says nothing about what the product does.

## Why Labwarden

- **Warden** = someone who keeps watch *and* steps in. That covers both halves of the product: monitoring and rescue (auto-heal, one-tap fixes).
- **Lab** ties it to homelab searches and to the community we serve.
- It is a **coined compound**, so searching the name returns us, not a dictionary entry.
- Short, easy to spell from hearing it, and works as a verb-free noun in sentences: "Labwarden restarted Jellyfin."

**Slogan:** The homelab warden that fixes things while you're away.
**Hero line (unchanged):** Know what happened while you were offline.

### Availability check (2026-10-08)

| Where | Result |
|---|---|
| PyPI, npm, Docker Hub (`labwarden`) | Free |
| `ghcr.io/xrg360/labwarden`, `github.com/xrg360/labwarden` | Free (under the existing account) |
| GitHub org `labwarden` | Taken (empty organization, created 2020) |
| GitHub repo name elsewhere | One archived-style legacy macOS lab-management repo (`execriez/LabWarden`, "Legacy code, zipped up for archive purposes"). Different domain and inactive. |
| `labwarden.dev`, `.io`, `.app` | Not resolving (likely unregistered; confirm with a registrar) |
| `labwarden.com` | Registered by someone else |
| Trademark search (web) | No "LabWarden" mark found. Confirm with USPTO/EUIPO (classes 9 and 42) before any paid marketing. |

## Search (SEO) plan

The name makes us findable *by name*. Rankings for what people actually type come from content:

- `<title>`: "Labwarden — Self-hosted homelab monitoring and auto-repair for Docker".
- Keywords in the metadata include "homelab monitoring", "uptime kuma alternative", "docker monitoring", "auto-heal docker" and the old name, so existing links and searches still land.
- Keep the `/compare/*` pages (Labwarden vs Uptime Kuma, Beszel, …). Comparison pages are what people search for when choosing a tool.
- Say "Formerly Meerkat" on the website and README for at least one year.
- Register `labwarden.dev` (or `.io`) and point it at the website; keep the old domain redirecting.

## Visual identity: Ink & Cream

- **Canvas:** warm cream (`#fffaf0`) with white cards and hairline grey borders. All neutrals are true greys; the old brown/sand tints are gone.
- **Ink:** near-black (`#0a0a0a`) for text, primary buttons, focus and selected states. In dark mode the canvas is a teal-tinted night (`#081414`) and the ink becomes cream.
- **Status:** green, amber and red are reserved for state, always with an icon and a word.
- **Brand palette:** teal, lavender, peach, ochre and pink for the logo and website feature cards only.
- **Type:** Inter if installed, otherwise the system font; display weight 600 with tight tracking. No downloaded web fonts.
- **Logo:** an ink shield carrying a cream pulse line, on an ochre rounded tile ("the warden mark").

The style draws on modern editorial SaaS sites (cream canvas, ink CTAs, saturated feature cards), adapted so that on the dashboard every hue still means status. It does not reuse any other company's logo, illustrations or mascots.

## Migrating from Meerkat

Existing installs keep working after upgrading:

| Old | New | Status |
|---|---|---|
| `MEERKAT_*` environment variables | `LABWARDEN_*` | Old names still read as a fallback |
| `/api/meerkat/*` proxy path | `/api/labwarden/*` | Old path rewritten to the new one |
| `X-Meerkat-Action-Token` header | `X-Labwarden-Action-Token` | Both accepted |
| `meerkat_*` Prometheus metrics | `labwarden_*` | Both emitted; old names **deprecated**, removed in a future minor release |
| Browser preferences (`meerkat.*` keys) | `labwarden.*` | Old values read automatically |
| Container name `meerkat` | `labwarden` | Both protected from restart and ignored by auto-heal by default |
| `ghcr.io/xrg360/meerkat` | `ghcr.io/xrg360/labwarden` | Update your compose file |

To switch an existing compose setup: change the image to `ghcr.io/xrg360/labwarden:latest`, optionally rename the service and container to `labwarden`, and rename `MEERKAT_*` variables to `LABWARDEN_*` when convenient. Update Grafana panels to the `labwarden_*` metric names before the deprecated ones are removed.
