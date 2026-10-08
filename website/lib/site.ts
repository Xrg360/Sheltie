// Website content and constants. Keep claims honest: anything not shipped is marked "planned".

export const SITE_URL = (process.env.SITE_URL || "https://meerkat.simplewebsite.in").replace(/\/$/, "");
export const REPO_URL = "https://github.com/xrg360/meerkat";
export const IMAGE = "ghcr.io/xrg360/meerkat";
export const VERSION = "0.2.0";

export const TAGLINE = "Know what happened while you were offline.";
export const DESCRIPTION =
  "Meerkat is a free, open-source monitoring agent for Docker homelabs. It watches websites, containers, network failover and host health, sends quiet Telegram alerts, repairs what it safely can, and shows a calm dashboard that tells you what is wrong and how to fix it.";

export const QUICK_START = `mkdir -p meerkat/config meerkat/state && cd meerkat
curl -fsSL ${REPO_URL}/raw/master/config/config.yml -o config/config.yml
docker run -d --name meerkat --restart unless-stopped \\
  --privileged --network host \\
  -v /var/run/docker.sock:/var/run/docker.sock:ro \\
  -v $(pwd)/config:/app/config -v $(pwd)/state:/app/state \\
  ${IMAGE}:latest`;

export type Feature = { title: string; body: string; icon: string; status?: "planned" };

export const FEATURES: Feature[] = [
  { icon: "sparkles", title: "Answers, not dashboards", body: "Every page opens with a plain sentence: “2 problems need attention”, “7 of 8 sites up”. The numbers come after." },
  { icon: "clock", title: "Since your last visit", body: "Open Meerkat after a day away and see exactly what happened: outages, recoveries, crashed containers and automatic repairs." },
  { icon: "wrench", title: "Fix it from the alert", body: "Problems come with the button that fixes them: start a crashed container, open the failing site, silence alerts for an hour." },
  { icon: "boxes", title: "Docker events and auto-heal", body: "Get told when containers die. Meerkat restarts the ones that crashed, and leaves alone the ones you stopped on purpose." },
  { icon: "network", title: "Network failover awareness", body: "Ethernet and Wi-Fi state, default-route changes and internet reachability, shown as a simple connection path." },
  { icon: "activity", title: "Website and service checks", body: "HTTP status, latency, redirects and keyword checks with heartbeat bars, uptime, average and p95 response time." },
  { icon: "cpu", title: "Host health", body: "CPU, memory, disk and CPU temperature with thresholds, durations and cooldowns so you only hear about real problems." },
  { icon: "send", title: "Two-way Telegram", body: "Quiet, state-change-only alerts, plus /status, /docker, /restart and /silence from your phone. Stale commands are ignored safely." },
  { icon: "smartphone", title: "Built for your phone", body: "Bottom tabs, bottom sheets and 44px touch targets. Install it to your home screen and check your lab from anywhere." },
  { icon: "command", title: "Fast for experts", body: "⌘K command palette, g-shortcuts, Prometheus /metrics and a REST API. Calm for beginners, quick for power users." },
  { icon: "shield", title: "Private and secure by default", body: "No telemetry, no external requests from the dashboard, and every action protected by a token generated on first start." },
  { icon: "accessibility", title: "Accessible", body: "WCAG 2.2 AA, checked automatically on every page. Status is never shown by color alone." },
  { icon: "inbox", title: "Offline alert outbox", body: "Alerts are stored and retried during internet outages, then summarized in one digest when you are back online.", status: "planned" },
  { icon: "zap", title: "Power-cut forensics", body: "On boot, Meerkat tells you whether the host crashed, rebooted or lost power, and for how long.", status: "planned" },
  { icon: "radar", title: "Off-site Sentinel", body: "A tiny watcher outside your home that alerts you when your whole lab goes dark.", status: "planned" },
];

export type Comparison = {
  slug: string;
  name: string;
  url: string;
  summary: string;
  theyAreGreatAt: string[];
  meerkatAdds: string[];
  chooseThem: string;
  chooseMeerkat: string;
  together: string;
};

export const COMPARISONS: Comparison[] = [
  {
    slug: "uptime-kuma",
    name: "Uptime Kuma",
    url: "https://github.com/louislam/uptime-kuma",
    summary: "Uptime Kuma is an excellent, very popular uptime monitor with many check types, 90+ notification providers and beautiful public status pages.",
    theyAreGreatAt: ["Many monitor types (HTTP, TCP, DNS, ping, push and more)", "Public status pages for your users", "A huge range of notification providers", "A large, mature community"],
    meerkatAdds: [
      "Host health (CPU, memory, disk, temperature) next to your checks",
      "Docker lifecycle events and intent-aware auto-heal",
      "Ethernet/Wi-Fi failover and default-route awareness",
      "“Since your last visit” and problems with fix-it buttons",
      "Two-way Telegram commands",
    ],
    chooseThem: "You mainly need many kinds of endpoint checks and a public status page.",
    chooseMeerkat: "You run a Docker homelab and want one calm place that tells you what broke on the box itself, and helps you fix it.",
    together: "Run both: point an Uptime Kuma push monitor at Meerkat's heartbeat to know when the whole host goes down.",
  },
  {
    slug: "beszel",
    name: "Beszel",
    url: "https://github.com/henrygd/beszel",
    summary: "Beszel is a lightweight hub-and-agent server monitor with clean charts for system and container resource usage.",
    theyAreGreatAt: ["Multi-server monitoring from one hub", "Historical resource charts per system and container", "A very small footprint", "Multi-user access"],
    meerkatAdds: ["Website and service checks with uptime and latency", "Container crash events and auto-heal", "Network failover awareness", "Plain-language status and actionable problems", "Two-way Telegram control"],
    chooseThem: "You want resource history across many servers.",
    chooseMeerkat: "You want to know when something breaks in your homelab and what to do about it, from your phone.",
    together: "Use Beszel for long-term resource graphs and Meerkat for incidents, repairs and alerts.",
  },
  {
    slug: "netdata",
    name: "Netdata",
    url: "https://github.com/netdata/netdata",
    summary: "Netdata collects thousands of metrics per second with deep, expert-grade dashboards and anomaly detection.",
    theyAreGreatAt: ["Per-second metrics for almost everything", "Deep diagnostics for experts", "Hundreds of integrations"],
    meerkatAdds: ["A calm, answer-first view instead of a chart wall", "Website checks and Docker crash events in one place", "Auto-heal and fix-it buttons", "A much smaller resource footprint"],
    chooseThem: "You need to diagnose why something is slow at a fine-grained level.",
    chooseMeerkat: "You need to know quickly that something broke and fix it, without reading charts.",
    together: "Use Meerkat for “is it broken?” and Netdata for “why is it slow?”. Meerkat also exposes Prometheus metrics.",
  },
];

export const FAQ = [
  { q: "Is Meerkat free?", a: "Yes. Meerkat is open source under the Apache-2.0 license, with no paid tier and no telemetry." },
  { q: "Does it run on a Raspberry Pi?", a: "Yes. Images are published for amd64 and arm64, and Meerkat is designed to be light enough for a Pi or mini-PC." },
  { q: "How is Meerkat different from Uptime Kuma?", a: "Uptime Kuma focuses on endpoint checks and status pages. Meerkat watches the homelab host itself (Docker, network, health), repairs what it safely can, and tells you what happened while you were away. Many people run both." },
  { q: "Do I need Telegram?", a: "No. The dashboard works on its own with in-app and desktop notifications. Telegram adds alerts and commands on your phone." },
  { q: "Will auto-heal restart containers I stopped on purpose?", a: "No. Meerkat tracks docker stop and compose stop and leaves those containers alone until you start them again." },
  { q: "Does the dashboard send data anywhere?", a: "No. It only talks to your own Meerkat API. No fonts, CDNs, analytics or trackers." },
];
