# Contributing to Labwarden

Thanks for helping Labwarden keep watch. Contributions of every size are welcome, from typo fixes to new monitors, notifiers and repair actions.

## Where to start

- Issues labelled [`good first issue`](https://github.com/xrg360/labwarden/labels/good%20first%20issue) are scoped to one evening.
- Issues labelled `plugin` are self-contained monitors, notifiers or actions (see [docs/ROADMAP.md](docs/ROADMAP.md#7-missing-features--contributor-backlog)).
- For anything larger, open a feature request first so the design can be agreed before you write code.

## Project layout

| Path | What lives there |
|---|---|
| `app.py` | Entry point: loads config, starts background monitors, runs the check loop |
| `monitors/alerts.py` | `AlertManager`: dedupe, duration, cooldown, recovery messages |
| `monitors/<check>.py` | One file per periodic check (`cpu`, `disk`, `sites`, `network`, ...) |
| `monitors/docker.py`, `autofix.py`, `commands.py` | Background threads: Docker events, auto-heal, Telegram commands |
| `monitors/api.py` | Python REST API, Prometheus `/metrics`, fallback dashboard |
| `src/` | Next.js dashboard: `components/ui` primitives, `components/shell` app frame, `components/pages` screens, `lib` data and copy |
| `website/` | Public website, docs and live demo (deployed to GitHub Pages) |
| `e2e/` | Playwright end-to-end and accessibility tests |
| `tests/` | `unittest` suite with in-memory fakes for state, history and notifiers |
| `docs/` | Architecture, roadmap and competitive analysis |

## Development setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
npm ci
```

Run the monitor API and the web app in two terminals:

```bash
LABWARDEN_API_PORT=8711 python app.py
npm run dev        # http://127.0.0.1:8710
```

Telegram is optional; without a token Labwarden logs the messages it would have sent.

## Checks to run before opening a PR

```bash
ruff check .
mypy --ignore-missing-imports app.py monitors
python -m unittest discover -v tests
npm run build      # only if you changed src/
```

CI runs the same commands plus a Docker image build.

## Adding a new periodic check

A check is a function with the signature `check_<name>(config, state, alerts) -> None`:

1. Read its settings from `config.get("<name>", {})`.
2. Store the latest reading with `state.set("metrics.<name>...", value)` so the API can show it.
3. Report the condition with `alerts.condition(alert_id=..., active=..., ...)` for threshold alerts, or `alerts.state_change(...)` for "value changed" alerts. Never call the notifier directly; `AlertManager` handles dedupe, duration, cooldown and recovery.
4. Register it in the `checks` list in `app.py` and validate new config keys in `monitors/config.py`.
5. Add tests using the `FakeState` / `FakeHistory` / `FakeNotifier` pattern in `tests/test_alerts.py`.

A formal plugin API (entry points with config schemas) is planned. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#plugin-interface-planned).

## UI work

The dashboard has a written design contract: **read [DESIGN.md](DESIGN.md) first**. It explains who Labwarden is for, the principles, the invariants that must not change, the Savanna tokens and the components to reuse.

```bash
npm run dev:demo         # dashboard with simulated data, no backend needed
npm run check:tokens     # no color literals outside src/styles/tokens.css
npm run check:contrast   # every token pair meets WCAG AA
npm run build:demo && npx playwright test   # e2e + axe accessibility on desktop and mobile
```

Attach light, dark and mobile screenshots to UI pull requests. Changes to the design contract itself go through a `design-rfc` issue.

## Style

- Python 3.12, type hints on public functions, `ruff` clean.
- Match the surrounding code: small modules, plain functions, result dicts `{"ok": bool, "message" | "error": str}` for actions.
- Anything that changes the host (restarts, interface bounces) must respect `actions.enabled`, `actions.blocked_containers` and the action token.

## Commit and PR conventions

- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `chore:`) so release notes can be generated.
- Keep one logical change per PR, and include a test for new behaviour.
- Fill in the PR template.

## Licensing

Labwarden is licensed under [Apache-2.0](LICENSE). By submitting a contribution you agree it is licensed under the same terms (Apache-2.0 section 5).

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind.
