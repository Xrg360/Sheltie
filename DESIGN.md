# Sheltie design system

This document is the contract for Sheltie's user experience. Read it before changing anything in `src/`. It applies equally to human contributors and to AI coding agents (see [AGENTS.md](AGENTS.md)).

The core promise: **Sheltie tells you what happened while you were away, what is wrong now, and what to do about it — in that order, in plain language, on any screen.**

Everything below exists to protect that promise. If a change makes Sheltie look different but keeps the promise, it is probably fine. If it weakens the promise, it is not, no matter how good it looks.

- [1. Who we design for](#1-who-we-design-for)
- [2. Principles](#2-principles)
- [3. Core UX invariants](#3-core-ux-invariants-do-not-change-without-a-design-rfc)
- [4. Tokens](#4-tokens)
- [5. Status language](#5-status-language)
- [6. Layout and navigation](#6-layout-and-navigation)
- [7. Components](#7-components)
- [8. Voice and tone](#8-voice-and-tone)
- [9. Accessibility](#9-accessibility)
- [10. Motion](#10-motion)
- [11. Performance and privacy budget](#11-performance-and-privacy-budget)
- [12. How to change this document](#12-how-to-change-this-document)
- [13. Review checklist](#13-review-checklist)

---

## 1. Who we design for

| Persona | Context | What they need from Sheltie |
|---|---|---|
| **Priya, the weekend homelabber** (primary) | Runs Nextcloud, Jellyfin and Home Assistant on a mini-PC or Raspberry Pi. Checks Sheltie from her **phone**, often away from home. Comfortable with Docker Compose, not a sysadmin. | A one-glance answer. Plain words, not alert IDs. A button that fixes the problem. Confidence that nothing happened while she was out. |
| **Marco, the tinkerer** (primary) | Rebuilds his stack often. Breaks things on purpose. | Sheltie must not fight him (no restarting things he stopped). Fast access via keyboard. |
| **Sam, the sysadmin** (secondary) | Manages a small office server and a VPS. | Density on demand, keyboard shortcuts, `/metrics`, exact timestamps on hover. |

Design for Priya first. Marco and Sam get speed through shortcuts and the command palette, never at the cost of Priya's clarity.

## 2. Principles

### 1. Answer before data
Every page starts with a sentence that answers the page's question. Numbers and charts come after.

| Do | Don't |
|---|---|
| "2 problems need attention" | A grid of 12 equal-weight tiles |
| "7 of 8 sites up" | "Monitors" as the page heading |
| "Internet is unreachable" | "internet_up: false" |

### 2. Color means status
The interface is **cream and ink**: a warm cream canvas, white cards with hairline borders, and neutral grey text with no brown or sand tints. Status colors (green, amber, red) appear only to communicate state, and are **always paired with an icon shape and a word**. **Ink is the interactive color**: primary buttons, focus rings, selected navigation and links are near-black in light mode and cream in dark mode. Because the accent is not a hue, links in running text are underlined.

The saturated **brand palette** (lavender, peach, ochre, pink, plus ink and cream) belongs to the logo and the website. It never appears on a dashboard surface, because on a dashboard every hue must mean something.

| Do | Don't |
|---|---|
| Neutral meters that turn amber/red only past a threshold | Decorative gradients, brand-colored cards or backgrounds in the dashboard |
| `✓ Up` pill (icon + word + color) | A green dot with no text |
| Up bars quiet, down bars full-strength red | Every bar shouting bright green |
| Ink primary button, one per view | A pink "Add monitor" button (pink reads as "down") |

### 3. Every problem has a next step
Anything shown as a problem offers at least one action: Restart/Start, Open site, View monitor, View network, Silence. If there is genuinely nothing to do in Sheltie, link to the place that explains it.

### 4. Honest about time
Every value has an age. The top bar always shows how fresh the data is ("Live · 4s ago"). When Sheltie cannot reach its backend, the UI says so in a banner and keeps showing the **last known state with its age** — it never shows stale data as if it were live, and never blanks the screen.

### 5. Calm by default, fast for experts
Generous spacing, one primary action per view, progressive disclosure (advanced options folded). Experts get the command palette (`⌘K` / `Ctrl+K` / `/`), `g` + letter navigation, and `?` for help.

## 3. Core UX invariants (do not change without a design RFC)

These are the non-negotiable parts of Sheltie's experience. A pull request that changes any of them must link an approved design RFC (a GitHub issue labelled `design-rfc` that the maintainer has approved). CODEOWNERS enforces review on the files that implement them.

1. **Status sentence first.** Every page renders a `PageHeader` whose `<h1>` is an answer sentence, with a `StatusGlyph` when the page has an overall state.
2. **Color never stands alone.** Status is always color + icon shape + text. Use `StatusPill`, `StatusIcon`, `StatusGlyph`.
3. **Problems carry actions.** Items in "Needs attention" always have at least one action button (`ProblemAction` in `src/lib/insights.ts`).
4. **"Since your last visit" stays on Overview.** It is Sheltie's signature feature.
5. **Data age is always visible**, and the offline/stale banner always appears when data is not live.
6. **Destructive or disruptive actions confirm first** (restart, remove, clear history, clear cache) via the shared confirm dialog. Removal offers Undo where possible.
7. **Navigation order and labels are fixed:** Overview · Incidents · Monitors · Containers · Network · Host · Settings (`src/lib/nav.ts`). Mobile bottom tabs: Overview, Incidents, Monitors, Containers, More.
8. **Tokens are the only color source.** No color literals outside `src/styles/tokens.css` (enforced by `npm run check:tokens`). Brand palette tokens are used only by the logo and the website.
9. **No external requests from the dashboard.** No web fonts, CDNs, analytics or trackers. Sheltie must work fully offline on a LAN. (`Inter` is named first in the font stack so it is used when installed locally; it is never downloaded.)
10. **Accessibility floor:** WCAG 2.2 AA, enforced by axe in CI, with no serious or critical violations.
11. **The logo** (`src/components/ui/logo.tsx`, `src/app/icon.svg`, `website/components/logo.tsx`) is the sheltie mark: an ink sheltie head with folded ear tips, a cream blaze and a cream collar, on an ochre rounded tile. Do not replace or recolor it.

## 4. Tokens

All tokens live in [`src/styles/tokens.css`](src/styles/tokens.css). Light, dark and system themes are defined there and nowhere else (the website imports the same file). Run `npm run check:contrast` after any change; every text pair must meet AA (4.5:1), every status/graphic color 3:1, and every brand-card text pair 4.5:1.

The palette is called **Ink & Cream**. It is inspired by modern editorial SaaS sites (cream canvas, ink CTAs, hairlines, generous radii), adapted so that status keeps sole ownership of hue.

### Color roles

| Role | Tokens | Use for |
|---|---|---|
| Canvas | `--bg` | Page background |
| Surfaces | `--surface`, `--surface-2`, `--surface-3` | Cards, inputs; sunken areas and alternate bands; tracks and skeletons |
| Lines | `--border`, `--border-strong` | Hairline dividers and card edges; input and button outlines |
| Text | `--text`, `--text-2`, `--text-3` | Primary; secondary; tertiary/meta (all AA on every surface) |
| Accent (ink) | `--accent`, `--accent-hover`, `--accent-soft`, `--accent-text`, `--on-accent`, `--focus` | Primary buttons, selected nav (cream-card fill + ink text), links, switches, focus rings, chart lines. **Never status.** |
| Status | `--ok*`, `--warn*`, `--bad*`, `--unknown*` | State only. `*-soft` for pill backgrounds, `*-text` for text on soft backgrounds |
| Brand | `--brand-ink`, `--brand-cream`, `--brand-lavender`, `--brand-peach`, `--brand-ochre`, `--brand-pink` | Logo and website only (see below) |

Reference values:

| Token | Light | Dark (neutral near-black) |
|---|---|---|
| `--bg` | `#fffaf0` cream | `#0c0c0d` |
| `--surface` / `-2` / `-3` | `#ffffff` / `#faf5e8` / `#f0eadb` | `#141416` / `#1b1b1e` / `#26262a` |
| `--border` / `-strong` | `#e5e5e5` / `#d4d4d4` | `#2a2a2e` / `#3f3f45` |
| `--text` / `-2` / `-3` | `#0a0a0a` / `#3a3a3a` / `#636363` | `#fffaf0` / `#cfccc4` / `#a3a09a` |
| `--accent` / `--on-accent` | `#0a0a0a` ink / `#ffffff` | `#fffaf0` cream / `#0a0a0a` |
| `--accent-soft` | `#f5f0e0` | `#26262a` |
| `--ok` / `--warn` / `--bad` | `#15803d` / `#b45309` / `#b91c1c` | `#4ade80` / `#fbbf24` / `#f87171` |
| `--unknown` | `#636363` | `#a3a09a` |

### Brand palette (logo and website only)

| Token | Value | Text on it |
|---|---|---|
| `--brand-ink` | `#0a0a0a` | `--brand-cream` |
| `--brand-lavender` | `#b8a4ed` | `--brand-ink` |
| `--brand-peach` | `#ffb084` | `--brand-ink` |
| `--brand-ochre` | `#e8b94a` | `--brand-ink` (also the logo tile) |
| `--brand-pink` | `#ff4d8b` | `--brand-ink` (white on pink fails AA) |

Rules:
- **Never in the dashboard.** Pink and coral read as "down", peach and ochre as "warning", mint as "up". Brand colors would break principle 2.
- On the website, brand feature cards cycle **ink → lavender → peach → ochre → pink** so that no two neighbours share a color (`website/components/features.tsx`). Ink cards, the ink CTA band and code blocks keep a hairline border so they stay visible in dark mode.
- No greens or teals in the brand palette: green belongs to the "up" status, and teal reads as green.
- Text on brand cards stays at full strength; don't use muted grey on a colored card.
- Buttons on the ink band invert: a cream-filled primary and cream-outline secondary.

### Typography
`--font-sans` is `Inter, ui-sans-serif, system-ui, …` (local only, never downloaded), with tabular numbers everywhere. Scale: 12 / 14 / 16 / 20 / 24 / 32 px (`--text-xs` … `--text-2xl`). Headings use `--weight-display` (600) with tight tracking: page headlines are 32px with `--tracking-display` (-0.025em), 24px on mobile; card titles 16px semibold; body 14px. Don't go heavier than 700 for display text; it reads as shouting.

The website uses a larger display scale: hero 40–72px (-0.04em), section heads 30–48px (-0.03em).

### Space, shape, elevation
- 4px grid: `--space-1` (4) to `--space-12` (48). Page padding 32px desktop, 16px mobile. Gaps between cards 24px. Website sections use a 96px rhythm.
- Radius: `--radius-sm` 8 (chips, small controls), `--radius-md` 12 (buttons, inputs, rows), `--radius-lg` 16 (cards, dialogs), `--radius-xl` 24 (website feature cards, bands, screenshots), `--radius-full` (pills).
- Elevation: depth comes from **hairline borders**, not shadows. `--shadow-1` is near-flat and only for cards; `--shadow-2` is for overlays (dialogs, popovers, palette) only.

## 5. Status language

| State | Tone | Icon | Words | Where |
|---|---|---|---|---|
| Healthy | `ok` | circle-check | Up · Running · Online · All systems normal | Pills, glyphs, uptime bars (muted) |
| Degraded / threshold | `warn` | triangle-alert | High · Almost full · Running hot | Meters past `warn`, warning alerts |
| Failing | `bad` | circle-x | Down · Exited · Unreachable · Problem | Pills, bars, problem items |
| Unknown / intentional | `unknown` | circle-help (or info) | Unknown · Stopped on purpose · Checking… | No data yet, user-stopped containers |

Thresholds: meters turn `warn` at 75% and `bad` at 90% by default (disk 80/90, CPU temperature 70/80 °C).

## 6. Layout and navigation

- **Desktop (> 860px):** 248px sidebar (logo, navigation with problem counts, docs/GitHub links, version) + sticky top bar (search/command trigger, connection indicator, silence menu) + content max 1200px.
- **Tablet (≤ 1100px):** two-column layouts collapse to one; monitor details open in a sheet.
- **Mobile (≤ 860px):** compact top bar, bottom tab bar (Overview, Incidents, Monitors, Containers, More), sheets slide up from the bottom, touch targets ≥ 44px, safe-area insets respected. The selected tab has a cream-card fill and bold label, not only a color change.
- **Page anatomy:** `PageHeader` (eyebrow, answer headline, meta, page actions) → primary content → secondary content.
- Overview layout: left column "Needs attention" then "Since your last visit"; right column "Vital signs" then "Pinned monitors". The setup checklist appears first only when nothing is wrong.

## 7. Components

Use the existing components; do not hand-roll equivalents. If you need something new, add it to `src/components/ui/` with a short usage note here.

| Component | File | Rules |
|---|---|---|
| `PageHeader` | `ui/layout.tsx` | Exactly one per page. Headline is a sentence, not a noun. |
| `Card` | `ui/layout.tsx` | White surface, hairline border. Title is a noun phrase. `tone` only for cards that contain problems. |
| `StatusPill` / `StatusIcon` / `StatusGlyph` / `Dot` | `ui/status.tsx` | The only way to show state. |
| `UptimeBars` | `ui/data.tsx` | One bar per check; down bars full height and red. Always has an `aria-label` summary. |
| `Meter` | `ui/data.tsx` | Neutral grey until a threshold. Shows the value as text. |
| `Sparkline` / `LatencyChart` | `ui/data.tsx` | Ink lines; red marks for down checks; hover/touch tooltip with exact values. |
| `Stat` | `ui/data.tsx` | Label + big value + sub line; link it when there is a detail page. |
| `Dialog` (`modal` / `sheet`) | `ui/dialog.tsx` | Native `<dialog>`. Sheets for forms and details; modals for confirmations. |
| Confirm, token prompt, toasts, palette | `shell/overlays.tsx`, `shell/command-palette.tsx` | Use `useSheltie().confirm()` and `toast()`; never `window.confirm` or `alert`. |
| `EmptyState` | `ui/layout.tsx` | Says what is missing and offers the next action. |
| `Segmented`, `SearchInput` | `ui/layout.tsx` | Filters show counts. |
| Buttons | `.btn`, `.btn--primary`, `.btn--ghost`, `.btn--danger` | One ink primary per view. Secondary buttons are white with a hairline. |
| Links | `a.link` or plain `<a>` | Underlined in running text. Links styled as buttons or rows use their own class. |
| Website `FeatureGrid` | `website/components/features.tsx` | Brand cards (`card--brand card--<tone>`), 24px radius, cycling tones. Website only. |

Data flows through `useSheltie()` (`src/lib/store.tsx`). Turning raw payloads into answers happens in `src/lib/insights.ts`. Copy lives in `src/lib/strings.ts`.

## 8. Voice and tone

- **Plain, calm, specific.** "Blog is down" not "site.blog.down ACTIVE". "Sheltie isn't responding" not "ERR_CONNECTION_REFUSED".
- **Say what happened, then what to do.** "Every probe host failed. Check the router or your ISP."
- **Sentence case** for headings and buttons. No exclamation marks. No blame ("you broke").
- **Verbs on buttons:** Restart, Start, Add monitor, Silence for 1 hour, Resume alerts, Open site. Not "OK", "Submit", "Execute".
- **Word list:** down (not DN/offline), up, running, stopped on purpose, needs attention, since your last visit, silence/resume (not mute/unmute).
- All strings go in `src/lib/strings.ts` so Sheltie can be translated.

## 9. Accessibility

- WCAG 2.2 AA minimum; axe runs on every page in CI on desktop and mobile.
- Every interactive element is reachable and operable by keyboard with a visible focus ring (`--focus`: ink in light mode, cream in dark mode, 2px with a 2px offset).
- Status is never conveyed by color alone (invariant 2). Selected states are never conveyed by color alone either (fill + weight).
- Charts and bars have text alternatives (`aria-label` summaries); meters use `role="meter"` with values.
- Live updates: toasts use `aria-live`, errors use `role="alert"`. Don't announce every poll.
- Respect `prefers-reduced-motion` and `prefers-color-scheme`.
- Minimum touch target 44×44px on mobile.

## 10. Motion

Motion explains change; it never decorates. Durations `--dur-fast` (120ms) and `--dur-base` (200ms) with `--ease`. Allowed: dialogs rising in, toasts appearing, meter widths easing, the live dot pulsing. Everything is disabled under reduced motion.

## 11. Performance and privacy budget

- First-load JavaScript per route ≤ 250 KB gzipped, of which the React/Next.js framework is about 150 KB. Enforced by `npm run check:bundle` in CI. The only runtime dependencies are React, Next.js and `lucide-react`.
- The dashboard makes requests only to its own `/api/sheltie/*` proxy (the pre-0.3 `/api/meerkat/*` path is rewritten to it). No third-party requests, fonts or telemetry.
- Polling pauses while the tab is hidden and backs off exponentially while the API is unreachable.
- Preferences live in `localStorage` and every access is wrapped in try/catch.

## 12. How to change this document

1. Open an issue labelled `design-rfc` describing the problem, the proposed change, before/after screenshots (light, dark, mobile) and which invariant it touches.
2. The maintainer (@xrg360) approves or declines.
3. Update this file and the implementation in the same PR, linking the RFC, and add a line to the decision log below.

Small additions that don't touch an invariant (a new component following existing rules, a new string) don't need an RFC, but still need review.

### Decision log

| Date | Decision | Invariants touched | Approved by |
|---|---|---|---|
| 2026-10-08 | Rename Meerkat → **Sheltie** (SEO: "Meerkat" competes with the animal, a 2015 livestream app and an ad campaign; a sheltie is a watchful herding dog, which fits monitoring and rescue). Replace the Savanna palette (sand, brown, indigo) with **Ink & Cream** (cream canvas, ink accent, neutral grey text and a neutral near-black dark mode, hairlines, brand palette for logo and website only). The sheltie mark replaces the meerkat lookout. Rationale in [docs/BRAND.md](docs/BRAND.md). | 8, 9 (font note), 11 | @xrg360 |

## 13. Review checklist

Copy into PRs that touch the UI:

- [ ] Each changed page still leads with an answer sentence (`PageHeader`).
- [ ] No new color literals; `npm run check:tokens` and `npm run check:contrast` pass.
- [ ] No brand palette colors (lavender, peach, ochre, pink) in the dashboard.
- [ ] Status shown with `StatusPill`/`StatusIcon` (color + icon + word).
- [ ] Every new problem state offers a next step.
- [ ] Destructive actions use `confirm()`.
- [ ] New strings added to `src/lib/strings.ts`.
- [ ] Works at 390px wide and with the keyboard only.
- [ ] `npm run build:demo && npx playwright test` passes (axe included).
- [ ] Screenshots attached: light, dark, mobile.
