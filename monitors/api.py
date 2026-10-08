import json
import logging
import hmac
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class ApiServer:
    def __init__(self, config: dict[str, Any], status_service: Any, action_service: Any) -> None:
        api_config = config.get("api", {}) or {}
        self.enabled = bool(api_config.get("enabled", True))
        self.host = str(api_config.get("host", "0.0.0.0"))
        self.port = int(os.getenv("MEERKAT_API_PORT") or api_config.get("port", 8710))
        self.status_service = status_service
        self.action_service = action_service
        self.action_token = resolve_action_token(config, status_service.state)
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            return

        status_service = self.status_service
        action_service = self.action_service
        action_token = self.action_token

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                routes = {
                    "/health": status_service.status,
                    "/status": status_service.status,
                    "/api/status": status_service.status,
                    "/api/health": status_service.health,
                    "/api/network": status_service.network,
                    "/api/docker": status_service.docker,
                    "/api/sites": status_service.sites,
                    "/api/events": lambda: {"events": status_service.history.recent(100)},
                    "/metrics": lambda: metrics_payload(status_service),
                    "/": lambda: dashboard_html("home"),
                    "/monitoring": lambda: dashboard_html("monitoring"),
                    "/settings": lambda: dashboard_html("settings"),
                }
                handler = routes.get(self.path.split("?")[0])
                if not handler:
                    self.send_response(404)
                    self.end_headers()
                    return

                payload = handler()
                if isinstance(payload, str):
                    content_type = "text/plain; charset=utf-8" if self.path == "/metrics" else "text/html; charset=utf-8"
                    self._write(200, payload.encode("utf-8"), content_type)
                    return
                self._write(200, json.dumps(payload, indent=2).encode("utf-8"), "application/json")

            def do_POST(self) -> None:
                if not self._authorized_action(action_token):
                    self._json({"ok": False, "error": "missing or invalid action token"}, status=403)
                    return

                path = self.path.split("?")[0]
                if path in ("/clearRamCache", "/api/actions/clear-ram-cache"):
                    self._json(action_service.clear_ram_cache())
                    return
                if path == "/api/actions/docker/restart":
                    body = self._read_json()
                    self._json(action_service.restart_container(str(body.get("container", ""))))
                    return
                if path == "/api/actions/sites/add":
                    self._json(action_service.add_site(self._read_json()))
                    return
                if path == "/api/actions/sites/remove":
                    body = self._read_json()
                    self._json(action_service.remove_site(str(body.get("name", ""))))
                    return
                if path == "/api/actions/events/clear":
                    self._json(action_service.clear_events())
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                logging.debug("api: " + format, *args)

            def _write(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, payload: dict[str, Any], status: int | None = None) -> None:
                status = status if status is not None else 200 if payload.get("ok", True) else 400
                self._write(status, json.dumps(payload, indent=2).encode("utf-8"), "application/json")

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length <= 0:
                    return {}
                if length > 4096:
                    return {}
                try:
                    return json.loads(self.rfile.read(length).decode("utf-8"))
                except json.JSONDecodeError:
                    return {}

            def _authorized_action(self, token: str | None) -> bool:
                if not token:
                    return False
                supplied = self.headers.get("X-Meerkat-Action-Token", "")
                return hmac.compare_digest(str(token), supplied)

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, name="api-server", daemon=True)
        self.thread.start()
        logging.info("API server listening on %s:%s", self.host, self.port)

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()


GENERATED_TOKEN_KEY = "api.action_token"


def resolve_action_token(config: dict[str, Any], state: Any) -> str:
    action_config = config.get("actions", {}) or {}
    configured = os.getenv("MEERKAT_ACTION_TOKEN") or action_config.get("token")
    if configured:
        return str(configured)

    generated = state.get(GENERATED_TOKEN_KEY)
    if generated:
        logging.warning(
            "No action token configured; using the auto-generated token stored in state under %s",
            GENERATED_TOKEN_KEY,
        )
        return str(generated)

    generated = secrets.token_urlsafe(32)
    state.set(GENERATED_TOKEN_KEY, generated)
    logging.warning(
        "No action token configured. Generated one for action endpoints: %s "
        "(set MEERKAT_ACTION_TOKEN to choose your own)",
        generated,
    )
    return generated


def metrics_payload(status_service: Any) -> str:
    health = status_service.health()
    status = status_service.status()
    network = status_service.network()
    sites = status_service.sites()
    lines = [
        "# HELP meerkat_cpu_percent Current CPU usage percent",
        "# TYPE meerkat_cpu_percent gauge",
        f"meerkat_cpu_percent {health['cpu_percent']}",
        "# HELP meerkat_ram_percent Current RAM usage percent",
        "# TYPE meerkat_ram_percent gauge",
        f"meerkat_ram_percent {health['ram_percent']}",
        "# HELP meerkat_disk_percent Current disk usage percent",
        "# TYPE meerkat_disk_percent gauge",
        f"meerkat_disk_percent {health['disk_percent']}",
        "# HELP meerkat_internet_up Internet reachability state",
        "# TYPE meerkat_internet_up gauge",
        f"meerkat_internet_up {1 if status.get('internet_up') else 0}",
        "# HELP meerkat_alerts_active Active alert count",
        "# TYPE meerkat_alerts_active gauge",
        f"meerkat_alerts_active {len(status.get('active_alerts', []))}",
        "# HELP meerkat_sites_up Number of configured sites currently up",
        "# TYPE meerkat_sites_up gauge",
        f"meerkat_sites_up {sites['up']}",
        "# HELP meerkat_sites_down Number of configured sites currently down",
        "# TYPE meerkat_sites_down gauge",
        f"meerkat_sites_down {sites['down']}",
    ]
    for label, details in network.get("interfaces", {}).items():
        lines.append(f'meerkat_network_interface_up{{interface="{details["name"]}",type="{label}"}} {1 if details["up"] else 0}')
    for site in sites.get("sites", []):
        name = str(site.get("name", "unknown")).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'meerkat_site_up{{name="{name}"}} {1 if site.get("up") else 0}')
        latency = site.get("latency_ms")
        if latency is not None:
            lines.append(f'meerkat_site_latency_ms{{name="{name}"}} {latency}')
    return "\n".join(lines) + "\n"


def dashboard_html(page: str = "home") -> str:
    page = page if page in {"home", "monitoring", "settings"} else "home"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Meerkat</title>
  <style>
    :root {{
      --bg: #eef3f8;
      --surface: #ffffff;
      --soft: #f7fafc;
      --ink: #111827;
      --muted: #667085;
      --line: #d8e0ea;
      --brand: #16b970;
      --brand-dark: #0d8d58;
      --bad: #dc3f3f;
      --warn: #d98b16;
      --blue: #2563eb;
      --shadow: 0 12px 28px rgba(17, 24, 39, .08);
    }}
    body[data-theme="dark"] {{
      --bg: #0d1218;
      --surface: #151d27;
      --soft: #101720;
      --ink: #edf2f7;
      --muted: #9aa6b2;
      --line: #273342;
      --shadow: none;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ min-width: 0; overflow-x: hidden; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }}
    a {{ color: inherit; text-decoration: none; }}
    button, input, select {{
      width: 100%;
      min-width: 0;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      color: var(--ink);
      padding: 0 12px;
      font: inherit;
    }}
    button {{ cursor: pointer; font-weight: 760; }}
    button:hover {{ border-color: var(--brand); }}
    input[type="radio"], input[type="checkbox"] {{ width: auto; min-height: 0; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; white-space: normal; }}
    .app {{ min-height: 100vh; display: grid; grid-template-columns: 260px minmax(0, 1fr); }}
    .sidebar {{
      min-width: 0;
      height: 100vh;
      position: sticky;
      top: 0;
      overflow: auto;
      padding: 18px;
      background: var(--surface);
      border-right: 1px solid var(--line);
    }}
    .brand {{ display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 12px; align-items: center; margin-bottom: 18px; }}
    .logo {{ width: 42px; height: 42px; border-radius: 8px; box-shadow: 0 10px 24px rgba(22, 185, 112, .22); }}
    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-size: 20px; line-height: 1.1; font-weight: 900; }}
    h2 {{ font-size: 22px; line-height: 1.2; font-weight: 900; }}
    h3 {{ font-size: 14px; font-weight: 850; }}
    .muted, .subtitle {{ color: var(--muted); }}
    .subtitle {{ margin-top: 4px; font-size: 12px; overflow-wrap: anywhere; }}
    .nav {{ display: grid; gap: 8px; margin-top: 18px; }}
    .nav a {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 42px;
      padding: 0 12px;
      border-radius: 8px;
      color: var(--muted);
      border: 1px solid transparent;
    }}
    .nav a.active {{ color: var(--ink); background: rgba(22, 185, 112, .12); border-color: rgba(22, 185, 112, .28); }}
    .content {{ min-width: 0; max-width: 1280px; width: 100%; padding: 22px; }}
    .topbar {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 14px; }}
    .top-actions {{ display: flex; width: auto; gap: 8px; flex-wrap: wrap; }}
    .top-actions a, .top-actions button {{
      width: auto;
      min-height: 38px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      padding: 0 12px;
      font-weight: 800;
    }}
    .primary {{ border-color: var(--brand) !important; background: var(--brand) !important; color: #fff !important; }}
    .grid {{ display: grid; gap: 14px; min-width: 0; }}
    .summary {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 14px; }}
    .two {{ grid-template-columns: minmax(0, 1.25fr) minmax(280px, .75fr); align-items: start; }}
    .card {{
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .card-body {{ padding: 16px; min-width: 0; }}
    .card-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
    }}
    .stat {{ min-height: 92px; padding: 14px; }}
    .label {{ color: var(--muted); font-size: 12px; margin-bottom: 8px; }}
    .value {{ font-size: 25px; font-weight: 900; line-height: 1.05; overflow-wrap: anywhere; }}
    .subvalue {{ color: var(--muted); font-size: 12px; margin-top: 8px; overflow-wrap: anywhere; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      width: auto;
      max-width: 100%;
      min-height: 26px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 8px;
      color: var(--muted);
      background: var(--soft);
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .dot {{ width: 7px; height: 7px; border-radius: 99px; background: var(--muted); flex: 0 0 auto; }}
    .dot.good {{ background: var(--brand); }}
    .dot.bad {{ background: var(--bad); }}
    .dot.warn {{ background: var(--warn); }}
    .status-mini {{
      display: inline-grid;
      place-items: center;
      min-width: 34px;
      height: 24px;
      border-radius: 999px;
      color: #fff;
      background: var(--brand);
      font-size: 11px;
      font-weight: 900;
    }}
    .status-mini.down {{ background: var(--bad); }}
    .status-mini.warn {{ background: var(--warn); }}
    .site-list {{ display: grid; gap: 10px; }}
    .site-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--soft);
      text-align: left;
    }}
    .site-name {{ font-weight: 900; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .site-url {{ color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .bars {{
      display: grid;
      grid-template-columns: repeat(24, minmax(0, 1fr));
      gap: 3px;
      min-width: 0;
      margin-top: 10px;
    }}
    .bars span {{ height: 22px; border-radius: 99px; background: var(--brand); min-width: 0; }}
    .bars span.down {{ background: var(--bad); }}
    .bars span.empty {{ background: var(--line); opacity: .75; }}
    .detail-title {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: start; }}
    .monitor-name {{ font-size: 25px; line-height: 1.12; font-weight: 900; overflow-wrap: anywhere; }}
    .metric-cards {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }}
    .metric-card {{ min-width: 0; padding: 13px; border: 1px solid var(--line); border-radius: 8px; background: var(--soft); text-align: center; }}
    .metric-card strong {{ display: block; margin-top: 5px; font-size: 21px; overflow-wrap: anywhere; }}
    .chart-wrap {{ height: 250px; }}
    #latencyChart {{ width: 100%; height: 100%; display: block; }}
    .metrics {{ display: grid; gap: 12px; }}
    .metric-row {{ display: grid; grid-template-columns: 70px minmax(0, 1fr) 58px; gap: 8px; align-items: center; }}
    .track {{ height: 10px; border-radius: 99px; background: var(--line); overflow: hidden; }}
    .fill {{ height: 100%; width: 0%; border-radius: inherit; background: var(--brand); }}
    .fill.warn {{ background: var(--warn); }}
    .fill.bad {{ background: var(--bad); }}
    .form-grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr) 96px; gap: 10px; }}
    .settings-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .field {{ display: grid; gap: 6px; min-width: 0; }}
    .field label {{ color: var(--muted); font-size: 12px; font-weight: 850; }}
    .check-row {{ display: flex; gap: 8px; align-items: center; min-height: 40px; }}
    .check-row input {{ flex: 0 0 auto; }}
    .table-scroll {{ max-width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }}
    th {{ color: var(--muted); font-size: 12px; font-weight: 850; }}
    .event {{ border-left: 3px solid var(--line); padding-left: 10px; min-width: 0; }}
    .event.critical, .event.emergency {{ border-left-color: var(--bad); }}
    .event.warning {{ border-left-color: var(--warn); }}
    .event.info {{ border-left-color: var(--blue); }}
    .event-title {{ font-weight: 850; overflow-wrap: anywhere; }}
    .event-meta, .event-body {{ overflow-wrap: anywhere; }}
    .event-meta {{ color: var(--muted); font-size: 12px; margin: 3px 0 5px; }}
    .event-body {{ line-height: 1.4; white-space: pre-wrap; }}
    .empty {{ color: var(--muted); padding: 10px 0; }}
    .toast-stack {{ position: fixed; right: 14px; bottom: 14px; z-index: 50; display: grid; gap: 10px; max-width: min(360px, calc(100vw - 28px)); }}
    .toast {{ background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--bad); border-radius: 8px; box-shadow: var(--shadow); padding: 12px; }}
    .skeleton {{
      overflow: hidden;
      color: transparent;
      background: linear-gradient(90deg, var(--soft), rgba(22, 185, 112, .12), var(--soft));
      background-size: 220% 100%;
      border-radius: 8px;
      animation: shimmer 1.35s ease-in-out infinite;
    }}
    .sk-line {{ height: 12px; width: 100%; margin-bottom: 10px; }}
    .sk-line.short {{ width: 46%; }}
    .sk-line.medium {{ width: 70%; }}
    .sk-value {{ height: 28px; width: 62%; margin: 8px 0 12px; }}
    @keyframes shimmer {{ 0% {{ background-position: 120% 0; }} 100% {{ background-position: -120% 0; }} }}
    @media (max-width: 960px) {{
      .app {{ display: block; }}
      .sidebar {{ position: relative; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }}
      .nav {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .summary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .two {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 560px) {{
      body {{ font-size: 13px; }}
      .sidebar, .content {{ padding: 12px; }}
      .nav {{ grid-template-columns: 1fr; }}
      .topbar, .card-head {{ display: grid; }}
      .top-actions {{ width: 100%; display: grid; grid-template-columns: 1fr 1fr; }}
      .top-actions a, .top-actions button {{ width: 100%; justify-content: center; }}
      .summary, .metric-cards, .settings-grid, .form-grid {{ grid-template-columns: 1fr; }}
      .card {{ box-shadow: none; }}
      .monitor-name {{ font-size: 22px; }}
      .detail-title {{ grid-template-columns: 1fr; }}
      .chart-wrap {{ height: 210px; }}
      .bars {{ grid-template-columns: repeat(18, minmax(0, 1fr)); }}
      .table-scroll {{ overflow: visible; }}
      table, thead, tbody, tr, th, td {{ display: block; width: 100%; }}
      thead {{ display: none; }}
      tr {{ border: 1px solid var(--line); border-radius: 8px; background: var(--soft); padding: 9px; margin-bottom: 10px; }}
      td {{ border-bottom: 0; padding: 5px 0; white-space: normal; overflow-wrap: anywhere; }}
      td[data-label] {{ display: grid; grid-template-columns: 82px minmax(0, 1fr); gap: 8px; }}
      td[data-label]::before {{ content: attr(data-label); color: var(--muted); font-size: 12px; font-weight: 850; }}
    }}
  </style>
</head>
<body data-page="{page}">
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <svg class="logo" viewBox="0 0 64 64" role="img" aria-label="Meerkat logo">
        <defs><linearGradient id="logoGradient" x1="8" y1="7" x2="56" y2="58" gradientUnits="userSpaceOnUse"><stop stop-color="#20c977"/><stop offset="1" stop-color="#2563eb"/></linearGradient></defs>
        <rect width="64" height="64" rx="12" fill="url(#logoGradient)"/>
        <path d="M18 45V22c0-4 3-7 7-7h14c4 0 7 3 7 7v23h-8V25l-6 17h-5l-6-17v20h-8Z" fill="#fff"/>
        <circle cx="24" cy="18" r="3" fill="#0e131b" opacity=".26"/><circle cx="40" cy="18" r="3" fill="#0e131b" opacity=".26"/>
      </svg>
      <div><h1>Meerkat</h1><div class="subtitle">Uptime and homelab monitoring</div></div>
    </div>
    <div class="pill"><span id="liveDot" class="dot"></span><span id="liveText">Loading</span><span id="refreshAge">--s</span></div>
    <nav class="nav">
      <a href="/" class="{"active" if page == "home" else ""}">Home <span>Overview</span></a>
      <a href="/monitoring" class="{"active" if page == "monitoring" else ""}">Monitoring <span>HTTP</span></a>
      <a href="/settings" class="{"active" if page == "settings" else ""}">Settings <span>Prefs</span></a>
    </nav>
  </aside>
  <main class="content">
    <div class="topbar">
      <div>
        <h2>{"Operations Home" if page == "home" else "HTTP Monitoring" if page == "monitoring" else "Settings"}</h2>
        <div class="subtitle">{"Clean system overview." if page == "home" else "Uptime bars, latency chart, and site controls." if page == "monitoring" else "Display, notifications, token, and dashboard preferences."}</div>
      </div>
      <div class="top-actions">
        <a href="/monitoring" class="primary">Monitoring</a>
        <button onclick="refresh()">Refresh</button>
      </div>
    </div>

    <section id="homePage" style="display: {"block" if page == "home" else "none"}">
      <div class="grid summary" id="summary">{skeleton_stats()}</div>
      <div class="grid two">
        <section class="card">
          <div class="card-head"><h3>Pinned Monitors</h3><a class="pill" href="/settings">Choose</a></div>
          <div class="card-body"><div class="site-list" id="pinnedSites">{skeleton_list()}</div></div>
        </section>
        <section class="card">
          <div class="card-head"><h3>Active Alerts</h3><span class="pill" id="alertMode">Loading</span></div>
          <div class="card-body" id="activeAlerts"><div class="skeleton sk-line"></div><div class="skeleton sk-line medium"></div></div>
        </section>
      </div>
    </section>

    <section id="monitoringPage" style="display: {"block" if page == "monitoring" else "none"}">
      <div class="grid two">
        <div class="grid">
          <section class="card">
            <div class="card-body">
              <div class="detail-title">
                <div><div class="monitor-name" id="selectedSiteName"><span class="skeleton sk-line medium" style="display:block;height:28px"></span></div><a class="site-url" id="selectedSiteUrl" href="#" target="_blank" rel="noreferrer"></a></div>
                <span class="status-mini warn" id="selectedSiteStatus">--</span>
              </div>
              <div class="bars" id="uptimeBars">{empty_bars(24)}</div>
              <div class="subtitle" id="checkCaption">Loading monitor data...</div>
              <div class="metric-cards">
                <div class="metric-card"><span class="muted">Response</span><strong id="currentLatency">--</strong></div>
                <div class="metric-card"><span class="muted">Average</span><strong id="averageLatency">--</strong></div>
                <div class="metric-card"><span class="muted">Uptime</span><strong id="uptimePercent">--</strong></div>
              </div>
            </div>
          </section>
          <section class="card">
            <div class="card-head"><h3>Response Time</h3><span class="pill">Recent samples</span></div>
            <div class="card-body chart-wrap"><svg id="latencyChart" role="img" aria-label="HTTP response time chart"></svg></div>
          </section>
          <section class="card">
            <div class="card-head"><h3>Add Site</h3><span class="pill" id="actionState">Ready</span></div>
            <div class="card-body"><div class="form-grid"><input id="siteNameInput" placeholder="Name"><input id="siteUrlInput" placeholder="https://example.com"><button class="primary" onclick="addSite()">Add</button></div></div>
          </section>
        </div>
        <div class="grid">
          <section class="card">
            <div class="card-head"><h3>Sites</h3><button onclick="removeSelectedSite()">Remove selected</button></div>
            <div class="card-body"><div class="site-list" id="siteList">{skeleton_list()}</div></div>
          </section>
          <section class="card">
            <div class="card-head"><h3>System Health</h3><span class="pill" id="tempState">Temperature --</span></div>
            <div class="card-body"><div class="metrics" id="metrics"><div class="skeleton sk-line"></div><div class="skeleton sk-line"></div><div class="skeleton sk-line"></div></div></div>
          </section>
        </div>
      </div>
    </section>

    <section id="settingsPage" style="display: {"block" if page == "settings" else "none"}">
      <div class="grid two">
        <section class="card">
          <div class="card-head"><h3>Preferences</h3><span class="pill">Browser local</span></div>
          <div class="card-body">
            <div class="settings-grid">
              <div class="field"><label for="themeSelect">Theme</label><select id="themeSelect" onchange="savePreferences()"><option value="light">Light</option><option value="dark">Dark</option></select></div>
              <div class="field"><label for="refreshSelect">Refresh interval</label><select id="refreshSelect" onchange="savePreferences()"><option value="5000">5 seconds</option><option value="10000">10 seconds</option><option value="30000">30 seconds</option></select></div>
              <div class="field"><label for="tokenInput">Action token</label><input id="tokenInput" placeholder="Only needed if configured"></div>
              <div class="field"><label>&nbsp;</label><button onclick="saveActionToken()">Save token</button></div>
              <div class="field"><label>Alert popups</label><label class="check-row"><input id="popupToggle" type="checkbox" onchange="savePreferences()"> Show in-app alert popups</label></div>
              <div class="field"><label>Desktop notifications</label><button onclick="enableNotifications()">Enable notifications</button></div>
            </div>
          </div>
        </section>
        <section class="card">
          <div class="card-head"><h3>Home Monitor Cards</h3><span class="pill">Pick what appears on Home</span></div>
          <div class="card-body"><div class="site-list" id="settingsSiteList">{skeleton_list()}</div></div>
        </section>
      </div>
    </section>
  </main>
</div>
<div class="toast-stack" id="toastStack"></div>
<script>
const page = "{page}";
let lastRefresh = 0;
let refreshTimer = null;
let latest = {{status: null, health: null, network: null, docker: null, sites: {{sites: []}}}};
let selectedSiteName = "";
let seenAlerts = new Set(JSON.parse(localStorage.getItem("meerkatSeenAlerts") || "[]"));
function esc(value) {{ return String(value ?? "").replace(/[&<>"']/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[ch])); }}
function pct(value) {{ return Math.round(Number(value || 0)); }}
function statusLabel(value) {{ return value === true ? "up" : value === false ? "down" : "unknown"; }}
function latencyText(value) {{ return value === null || value === undefined ? "--" : `${{Math.round(value)}}ms`; }}
function siteHistory(site) {{ return Array.isArray(site?.history) ? site.history : []; }}
function avgLatency(site) {{ const s = siteHistory(site).map(x => x.latency_ms).filter(x => x !== null && x !== undefined); return s.length ? s.reduce((a,b) => a + Number(b), 0) / s.length : null; }}
function uptime(site) {{ const s = siteHistory(site); if (!s.length) return site?.up ? 100 : 0; return Math.round(s.filter(x => x.up === true).length / s.length * 1000) / 10; }}
function prefs() {{ return JSON.parse(localStorage.getItem("meerkatUiPrefs") || "{{}}"); }}
function selectedSite() {{ const sites = latest.sites.sites || []; return sites.find(site => site.name === selectedSiteName) || sites[0] || null; }}
function statusMini(site) {{ return `<span class="status-mini ${{site?.up ? "" : "down"}}">${{site?.up ? "UP" : "DN"}}</span>`; }}
function bars(site, count = 24) {{
  const samples = siteHistory(site).slice(-count);
  const padded = Array(Math.max(0, count - samples.length)).fill(null).concat(samples);
  return padded.map(s => !s ? "<span class='empty'></span>" : `<span class="${{s.up ? "" : "down"}}"></span>`).join("");
}}
function metric(name, value, suffix = "%") {{
  const v = pct(value), cls = v >= 90 ? "bad" : v >= 75 ? "warn" : "";
  return `<div class="metric-row"><div class="muted">${{esc(name)}}</div><div class="track"><div class="fill ${{cls}}" style="width:${{Math.max(0, Math.min(100, v))}}%"></div></div><div>${{v}}${{suffix}}</div></div>`;
}}
function applyPreferences() {{
  const p = prefs();
  document.body.dataset.theme = p.theme || "light";
  const theme = document.getElementById("themeSelect");
  const refresh = document.getElementById("refreshSelect");
  const token = document.getElementById("tokenInput");
  const popup = document.getElementById("popupToggle");
  if (theme) theme.value = p.theme || "light";
  if (refresh) refresh.value = String(p.refresh || 10000);
  if (token) token.value = localStorage.getItem("meerkatActionToken") || "";
  if (popup) popup.checked = p.popups !== false;
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(refresh, Number(p.refresh || 10000));
}}
function savePreferences() {{
  const p = prefs();
  const theme = document.getElementById("themeSelect");
  const refresh = document.getElementById("refreshSelect");
  const popup = document.getElementById("popupToggle");
  localStorage.setItem("meerkatUiPrefs", JSON.stringify({{theme: theme ? theme.value : p.theme || "light", refresh: refresh ? Number(refresh.value) : p.refresh || 10000, popups: popup ? popup.checked : p.popups !== false}}));
  applyPreferences();
}}
function saveActionToken() {{
  const token = document.getElementById("tokenInput").value.trim();
  if (token) localStorage.setItem("meerkatActionToken", token); else localStorage.removeItem("meerkatActionToken");
  showToast("Action token", token ? "Saved for this browser." : "Cleared.");
}}
function pinnedNames() {{ return new Set(JSON.parse(localStorage.getItem("meerkatPinnedSites") || "[]")); }}
function togglePin(name) {{
  const pins = pinnedNames();
  if (pins.has(name)) pins.delete(name); else pins.add(name);
  localStorage.setItem("meerkatPinnedSites", JSON.stringify([...pins]));
  renderAll();
}}
function enableNotifications() {{
  if (!("Notification" in window)) {{ showToast("Notifications unavailable", "This browser does not support desktop notifications."); return; }}
  Notification.requestPermission().then(result => showToast("Desktop notifications", result));
}}
function showToast(title, body) {{
  const node = document.createElement("div");
  node.className = "toast";
  node.innerHTML = `<div class="event-title">${{esc(title)}}</div><div class="event-body">${{esc(body)}}</div>`;
  document.getElementById("toastStack").appendChild(node);
  setTimeout(() => node.remove(), 8000);
}}
function alertUser(event) {{
  const p = prefs();
  if (p.popups !== false) showToast(event.title || "Alert", event.body || event.severity || "");
  if ("Notification" in window && Notification.permission === "granted") new Notification(event.title || "Meerkat alert", {{body: event.body || event.severity || ""}});
}}
function drawLoadingChart() {{
  const svg = document.getElementById("latencyChart"); if (!svg) return;
  svg.setAttribute("viewBox", "0 0 720 240");
  svg.innerHTML = `<rect width="720" height="240" rx="8" fill="var(--soft)"></rect><polyline points="46,172 140,146 232,156 326,112 420,128 514,82 612,104 704,72" fill="none" stroke="var(--brand)" stroke-width="3" stroke-linecap="round" opacity=".35"></polyline><text x="24" y="34" fill="var(--muted)" font-size="12">Loading response data...</text>`;
}}
function drawChart(samples) {{
  const svg = document.getElementById("latencyChart"); if (!svg) return;
  const values = samples.filter(s => s.latency_ms !== null && s.latency_ms !== undefined).slice(-60);
  if (!values.length) {{ drawLoadingChart(); return; }}
  const width = 720, height = 240, pad = {{left:44,right:16,top:16,bottom:34}};
  const max = Math.max(...values.map(s => Number(s.latency_ms)), 10), min = Math.min(...values.map(s => Number(s.latency_ms)), 0), range = Math.max(1, max - min);
  const step = values.length > 1 ? (width - pad.left - pad.right) / (values.length - 1) : 0;
  const points = values.map((s,i) => `${{(pad.left + i * step).toFixed(1)}},${{(height - pad.bottom - ((Number(s.latency_ms) - min) / range) * (height - pad.top - pad.bottom)).toFixed(1)}}`).join(" ");
  svg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);
  svg.innerHTML = `<polyline points="${{pad.left}},${{height-pad.bottom}} ${{points}} ${{width-pad.right}},${{height-pad.bottom}}" fill="rgba(22,185,112,.12)" stroke="none"></polyline><polyline points="${{points}}" fill="none" stroke="var(--brand)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline><text x="8" y="24" fill="var(--muted)" font-size="11">${{Math.round(max)}}ms</text><text x="${{pad.left}}" y="${{height-9}}" fill="var(--muted)" font-size="11">older</text><text x="${{width-pad.right-34}}" y="${{height-9}}" fill="var(--muted)" font-size="11">now</text>`;
}}
function renderSiteCard(site, opts = {{pin: false}}) {{
  return `<button class="site-row" onclick="selectSite('${{esc(site.name)}}')"><div><div class="site-name">${{esc(site.name)}}</div><div class="site-url">${{esc(site.url)}}</div><div class="bars">${{bars(site, 18)}}</div></div>${{statusMini(site)}}</button>${{opts.pin ? `<label class="check-row"><input type="checkbox" ${{pinnedNames().has(site.name) ? "checked" : ""}} onchange="togglePin('${{esc(site.name)}}')"> Show on Home</label>` : ""}}`;
}}
function renderAll() {{
  const status = latest.status, health = latest.health, docker = latest.docker, sites = latest.sites;
  if (!status || !health || !docker || !sites) return;
  const running = docker.containers.filter(c => c.status === "running").length;
  const summary = document.getElementById("summary");
  if (summary) summary.innerHTML = [
    ["Internet", statusLabel(status.internet_up), status.internet_up ? "Reachable" : "Probe failing"],
    ["Alerts", status.active_alerts.length, status.alerts_silenced ? "Silenced" : "Active"],
    ["Containers", `${{running}}/${{docker.containers.length}}`, docker.available ? "Docker connected" : "Docker unavailable"],
    ["Sites", `${{sites.up}}/${{sites.total}}`, sites.down ? `${{sites.down}} down` : "All up"]
  ].map(x => `<section class="card stat"><div class="label">${{esc(x[0])}}</div><div class="value">${{esc(x[1])}}</div><div class="subvalue">${{esc(x[2])}}</div></section>`).join("");
  const allSites = sites.sites || [];
  if (!selectedSiteName && allSites.length) selectedSiteName = allSites[0].name;
  const pins = pinnedNames();
  const pinned = allSites.filter(site => pins.has(site.name)).slice(0, 4);
  const pinnedNode = document.getElementById("pinnedSites");
  if (pinnedNode) pinnedNode.innerHTML = (pinned.length ? pinned : allSites.slice(0, 2)).map(renderSiteCard).join("") || "<div class='empty'>No monitors yet.</div>";
  const siteList = document.getElementById("siteList");
  if (siteList) siteList.innerHTML = allSites.map(renderSiteCard).join("") || "<div class='empty'>No monitors yet.</div>";
  const settingsList = document.getElementById("settingsSiteList");
  if (settingsList) settingsList.innerHTML = allSites.map(site => renderSiteCard(site, {{pin: true}})).join("") || "<div class='empty'>Add monitors from the Monitoring page.</div>";
  renderSelectedSite();
  const metrics = document.getElementById("metrics");
  if (metrics) metrics.innerHTML = [metric("CPU", health.cpu_percent), metric("RAM", health.ram_percent), metric("Disk", health.disk_percent), health.cpu_temperature == null ? "" : metric("Temp", health.cpu_temperature, "C")].join("");
  const tempState = document.getElementById("tempState");
  if (tempState) tempState.textContent = `CPU ${{health.cpu_temperature == null ? "unavailable" : Math.round(health.cpu_temperature) + "C"}}`;
  const activeAlerts = document.getElementById("activeAlerts");
  if (activeAlerts) activeAlerts.innerHTML = status.active_alerts.length ? status.active_alerts.map(a => `<div class="event critical"><div class="event-title">${{esc(a)}}</div><div class="event-meta">currently active</div></div>`).join("") : "<div class='empty'>No active alerts.</div>";
  const alertMode = document.getElementById("alertMode");
  if (alertMode) alertMode.textContent = status.alerts_silenced ? "Silenced" : "Active";
}}
function renderSelectedSite() {{
  const site = selectedSite();
  if (!site || page !== "monitoring") return;
  document.getElementById("selectedSiteName").textContent = site.name;
  const url = document.getElementById("selectedSiteUrl");
  url.textContent = site.url;
  url.href = site.url;
  const badge = document.getElementById("selectedSiteStatus");
  badge.textContent = site.up ? "UP" : "DN";
  badge.className = `status-mini ${{site.up ? "" : "down"}}`;
  document.getElementById("uptimeBars").innerHTML = bars(site, window.matchMedia("(max-width: 560px)").matches ? 18 : 24);
  document.getElementById("checkCaption").textContent = `HTTP ${{site.status_code ?? "none"}} - ${{site.error || "latest check completed"}}`;
  document.getElementById("currentLatency").textContent = latencyText(site.latency_ms);
  document.getElementById("averageLatency").textContent = latencyText(avgLatency(site));
  document.getElementById("uptimePercent").textContent = `${{uptime(site)}}%`;
  drawChart(siteHistory(site));
}}
function selectSite(name) {{
  selectedSiteName = name;
  if (page !== "monitoring") location.href = `/monitoring?site=${{encodeURIComponent(name)}}`;
  else renderSelectedSite();
}}
async function refresh() {{
  try {{
    const [status, health, network, docker, sites] = await Promise.all([fetch("/api/status").then(r => r.json()), fetch("/api/health").then(r => r.json()), fetch("/api/network").then(r => r.json()), fetch("/api/docker").then(r => r.json()), fetch("/api/sites").then(r => r.json())]);
    latest = {{status, health, network, docker, sites}};
    lastRefresh = Date.now();
    document.getElementById("liveDot").className = "dot good";
    document.getElementById("liveText").textContent = "Live";
    const params = new URLSearchParams(location.search);
    if (params.get("site")) selectedSiteName = params.get("site");
    renderAll();
    status.recent_events.filter(e => ["critical", "emergency", "warning"].includes(e.severity)).slice(0, 5).forEach(e => {{
      const key = `${{e.ts}}:${{e.alert_id}}:${{e.status}}`;
      if (!seenAlerts.has(key)) {{ seenAlerts.add(key); alertUser(e); }}
    }});
    localStorage.setItem("meerkatSeenAlerts", JSON.stringify([...seenAlerts].slice(-100)));
  }} catch (error) {{
    document.getElementById("liveDot").className = "dot bad";
    document.getElementById("liveText").textContent = "Offline";
  }}
}}
async function postJson(url, body = {{}}) {{
  const token = localStorage.getItem("meerkatActionToken");
  const headers = {{"Content-Type": "application/json"}};
  if (token) headers["X-Meerkat-Action-Token"] = token;
  const response = await fetch(url, {{method: "POST", headers, body: JSON.stringify(body)}});
  const payload = await response.json();
  if (!payload.ok) showToast("Action failed", payload.error || "Request failed");
  else showToast("Done", payload.message || "Action completed");
  await refresh();
}}
async function addSite() {{
  const name = document.getElementById("siteNameInput").value.trim();
  const url = document.getElementById("siteUrlInput").value.trim();
  if (!name || !url) {{ showToast("Missing site details", "Name and URL are required."); return; }}
  await postJson("/api/actions/sites/add", {{name, url}});
  selectedSiteName = name;
  document.getElementById("siteNameInput").value = "";
  document.getElementById("siteUrlInput").value = "";
}}
async function removeSelectedSite() {{
  const site = selectedSite();
  if (!site) {{ showToast("No site selected", "Select a runtime site first."); return; }}
  await postJson("/api/actions/sites/remove", {{name: site.name}});
  selectedSiteName = "";
}}
applyPreferences();
drawLoadingChart();
refresh();
setInterval(() => {{ document.getElementById("refreshAge").textContent = lastRefresh ? `${{Math.floor((Date.now() - lastRefresh) / 1000)}}s` : "--s"; }}, 1000);
window.addEventListener("resize", renderSelectedSite);
</script>
</body>
</html>"""


def skeleton_stats() -> str:
    return "".join(
        "<section class='card stat'><div class='skeleton sk-line short'></div><div class='skeleton sk-value'></div><div class='skeleton sk-line medium'></div></section>"
        for _ in range(4)
    )


def skeleton_list() -> str:
    return "".join("<div class='skeleton' style='height:68px'></div>" for _ in range(3))


def empty_bars(count: int) -> str:
    return "".join("<span class='empty'></span>" for _ in range(count))

