## What does this change?

<!-- One or two sentences. Link the issue it closes: Closes #123 -->

## How was it tested?

- [ ] `python -m unittest discover tests`
- [ ] `ruff check .` and `mypy --ignore-missing-imports app.py monitors`
- [ ] `npm run build` (if the web UI changed)
- [ ] Tried it on a real host (describe below)

## UI changes (skip if none)

- [ ] Followed [DESIGN.md](../DESIGN.md); no core UX invariant changed (or linked design RFC: #)
- [ ] `npm run check:tokens`, `npm run check:contrast` and `npx playwright test` pass
- [ ] Screenshots attached: light, dark, mobile (390px)

## Checklist

- [ ] New behaviour has a unit test
- [ ] README / docs updated for new config keys or commands
- [ ] No secrets, tokens or personal hostnames in the diff
