# Launch and discoverability checklist

Things only the repository owner can do (they need GitHub settings, DNS or personal accounts). Tick them off in order; together they are what makes Meerkat findable.

## 1. Repository settings (10 minutes)

- [ ] **About → Description:**
  `Self-hosted homelab monitoring that tells you what happened while you were offline: uptime, Docker, network failover, auto-heal and Telegram alerts.`
- [ ] **About → Website:** `https://meerkat.simplewebsite.in`
- [ ] **About → Topics:** `homelab` `self-hosted` `monitoring` `uptime-monitor` `docker` `telegram-bot` `raspberry-pi` `alerting` `auto-heal` `status-page` `prometheus` `uptime-kuma-alternative` `power-outage` `nextjs` `python`
- [ ] **Settings → General → Social preview:** upload [`docs/assets/social-preview.png`](assets/social-preview.png) (1280×640).
- [ ] **Settings → General → Features:** enable **Discussions** (the issue templates link to it).
- [ ] **Settings → Code security:** enable **Private vulnerability reporting** (SECURITY.md points to it), Dependabot alerts and secret scanning.
- [ ] **Settings → Branches:** protect `master`: require PRs, require the CI checks, require review from Code Owners.

## 2. Website on the custom domain

- [ ] DNS for `simplewebsite.in`: add `CNAME meerkat → xrg360.github.io`.
- [ ] **Settings → Pages:** Source **GitHub Actions**, custom domain `meerkat.simplewebsite.in`, then **Enforce HTTPS**.
- [ ] Merge the PR, then confirm the **Website** workflow deployed and `https://meerkat.simplewebsite.in/demo/` opens.
- [ ] Add the site to **Google Search Console** and **Bing Webmaster Tools**, and submit `https://meerkat.simplewebsite.in/sitemap.xml`.

## 3. First release

- [ ] Tag `v0.2.0` (`git tag v0.2.0 && git push origin v0.2.0`). The release workflow publishes `ghcr.io/xrg360/meerkat:0.2.0` and `:latest` for amd64 and arm64.
- [ ] Make the GHCR package **public** (Packages → meerkat → Package settings → Change visibility).
- [ ] Write GitHub release notes with the hero screenshot and a link to the live demo.

## 4. Community scaffolding

- [ ] Create labels: `good first issue`, `help wanted`, `plugin`, `design-rfc`, `bug`, `enhancement`, `triage`.
- [ ] Open 10–15 issues from the [roadmap backlog](ROADMAP.md#7-missing-features--contributor-backlog), each with the expected config, behaviour and a pointer to similar code. Label the small ones `good first issue`.
- [ ] Pin a "Roadmap" issue and a "Show us your setup" discussion.

## 5. Launch posts (one per week, not all at once)

Lead with the story, not the feature list: *"My ISP dropped overnight and my dashboard told me nothing. So I built one that tells you what happened while you were away."* Include the hero screenshot and the live demo link.

- [ ] r/selfhosted (Saturday morning US time tends to work best)
- [ ] r/homelab
- [ ] Show HN: `Show HN: Meerkat – homelab monitoring that tells you what happened while you were offline`
- [ ] selfh.st newsletter submission
- [ ] AlternativeTo: list Meerkat as an alternative to Uptime Kuma, Beszel and Netdata
- [ ] Product Hunt (after the outbox/digest feature ships, so the story is complete)
- [ ] awesome-selfhosted (eligible about 4 months after the first release; needs the license and a working demo)
- [ ] awesome-homelab and awesome-docker lists

## 6. Keep the momentum

- [ ] Monthly release with a "contributors this month" shout-out.
- [ ] Reply to every new issue within 48 hours, even just to label it.
- [ ] Share contributor PRs on social media.
- [ ] Track stars, clones and referrers in **Insights → Traffic** to see which posts worked.
