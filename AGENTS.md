# Instructions for AI coding agents

These rules apply to any automated agent (coding assistants, bots, autonomous PR tools) working in this repository. Humans should follow them too.

## Before you change anything

1. Read [DESIGN.md](DESIGN.md) if your change touches `src/`, and [CONTRIBUTING.md](CONTRIBUTING.md) for everything else.
2. Find the existing component or helper before writing a new one: `src/components/ui/`, `src/components/shell/`, `src/lib/`.

## Hard rules

- **Do not change the core UX invariants** listed in DESIGN.md section 3 (status sentence first, color never alone, problems carry actions, "Since your last visit", data age and offline banner, confirm before destructive actions, navigation order, tokens as the only color source, no external requests, accessibility floor, the logo). If a task seems to require it, stop and ask for a `design-rfc` issue instead.
- **Do not edit `src/styles/tokens.css`, `DESIGN.md` or the logo** unless the task explicitly says so and links an approved RFC.
- **No color literals** outside `src/styles/tokens.css`. Use tokens.
- **No new runtime dependencies** in the dashboard without approval. No web fonts, CDNs, analytics or external requests.
- **All user-facing strings** go in `src/lib/strings.ts`, written in the voice described in DESIGN.md section 8.
- **Destructive actions** (restart, remove, clear) must go through `useMeerkat().confirm()`.
- **Backend payload changes** must be mirrored in `src/lib/types.ts` and `src/lib/demo-data.ts`, and covered by a Python test in `tests/`.
- Do not weaken tests, axe rules or lint settings to make CI pass.

## Checks to run before you finish

```bash
# Python
ruff check . && mypy --ignore-missing-imports app.py monitors && python -m unittest discover tests
# Dashboard
npm run typecheck && npm run check:tokens && npm run check:contrast
npm run build && npm run build:demo && npx playwright test
```

## What to include in your PR

- What changed and why, in plain language.
- For UI changes: screenshots in light, dark and mobile (390px), and the DESIGN.md review checklist (section 13) ticked.
- Commits in Conventional Commits style (`feat:`, `fix:`, `docs:` …).
