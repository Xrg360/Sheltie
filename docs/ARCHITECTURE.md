# Sheltie architecture

This document describes how Sheltie works today and the architecture it is moving towards. The target design is built around one promise: **Sheltie tells you what happened while you were offline**, whether the cause was a dropped ISP link, a power cut, or the server itself being down.

- [Current architecture](#current-architecture)
- [Target architecture](#target-architecture)
- [Failure scenarios](#failure-scenarios)
- [Plugin interface (planned)](#plugin-interface-planned)
- [Storage model (planned)](#storage-model-planned)

---

## Current architecture

```mermaid
flowchart LR
  subgraph Container["sheltie container - privileged, host network"]
    direction TB
    NEXT["Next.js :8710<br/>proxy /api/sheltie/*"] -->|HTTP| API["Python stdlib HTTP :8711<br/>monitors/api.py"]
    MAIN["app.py main loop<br/>sequential checks every 30s"] --> AM["AlertManager"]
    DOCK["DockerEventMonitor thread"] --> AM
    HEAL["AutoHeal thread - 5m"] --> AM
    CMD["Telegram long-poll thread"]
    AM --> TG["TelegramNotifier<br/>fire-and-forget"]
    AM --> HIST[("history.db")]
    MAIN --> STATE[("state.json<br/>rewritten on every set")]
    AM --> STATE
    HEAL --> STATE
    CMD --> STATE
  end
  TG -->|HTTPS| TAPI["api.telegram.org"]
  DOCK -->|docker.sock| DOCKERD["dockerd"]
  HEAL -->|docker.sock| DOCKERD
```

| Component | File | Notes |
|---|---|---|
| Check loop | `app.py` | Runs `network`, `internet`, `cpu`, `ram`, `disk`, `temperature`, `sites` one after another, then sleeps `interval` seconds. |
| Alert engine | `monitors/alerts.py` | `condition()` (threshold with duration and cooldown), `state_change()` (value changed), `event()` (one-off). Every alert goes to history and then to Telegram. |
| State | `monitors/state.py` | A flat key/value dict persisted as JSON. |
| History | `monitors/history.py` | SQLite `events` table in WAL mode. Falls back to memory if the DB is broken. |
| Docker events | `monitors/docker.py` | Streams container lifecycle events. It also records containers stopped on purpose so auto-heal leaves them alone. |
| Auto-heal | `monitors/autofix.py` | Restarts containers that were running and then crashed, and bounces interfaces that have a link but lost their address. |
| Chat-ops | `monitors/commands.py` | Telegram long-polling. Destructive commands older than `telegram.command_max_age` (5 minutes by default) are ignored. |
| API | `monitors/api.py` | REST and Prometheus `/metrics`. Action endpoints always require a token, which is auto-generated if none is configured. |

### Known structural limits

These limits are what the target architecture removes:

1. Notifications are fire-and-forget. A Telegram send that fails during an outage is lost.
2. Writing `state.json` on every `set()` is slow, wears SD cards, and is not crash-safe.
3. Nothing records *when* the host went down or *why*.
4. Checks run in sequence, so one slow site delays every other check.
5. Two runtimes (Python and Node) share one container without a supervisor.

---

## Target architecture

The agent stays in **Python** because it is contributor-friendly, already works, and has access to Apprise's 100+ notification services. It becomes **one asyncio process** under `tini`, with the web UI served as a static Next.js export by the same process.

```mermaid
flowchart TB
  subgraph Agent["sheltie-agent - single asyncio process, tini as PID 1"]
    direction TB
    SCHED["Scheduler<br/>per-monitor interval and jitter<br/>timeouts, concurrency limit<br/>monotonic clock"]
    subgraph Plugins["Plugin registry - Python entry points"]
      MON["Monitors<br/>cpu ram disk temp iface route<br/>gateway dns wan http tcp tls<br/>docker-events docker-health ups smart"]
      ACT["Actions<br/>container start and restart<br/>iface bounce, script hooks"]
      NOTI["Notifiers<br/>Telegram, Apprise, webhook<br/>ntfy LAN, web push, MQTT"]
    end
    SCHED --> MON
    MON -->|Observation| ENG["Alert engine<br/>ok - pending - firing - resolved<br/>dedupe, flap detection, maintenance windows<br/>silence with expiry, dependencies"]
    ENG --> DB[("SQLite WAL, synchronous FULL<br/>kv_state, events, metrics rollups<br/>outbox, heartbeats")]
    ENG --> HEALER["Auto-heal policy<br/>opt-in labels, intent-aware<br/>backoff and max attempts"]
    HEALER --> ACT
    DB --> DISP["Outbox dispatcher<br/>retry with backoff and jitter<br/>per-channel rate limit<br/>digest, channel failover"]
    DISP --> NOTI
    LIFE["Lifecycle<br/>heartbeat every 30s<br/>clean-shutdown marker<br/>boot forensics"] --> DB
    LIFE --> SCLIENT["Sentinel client<br/>outbound heartbeat and snapshot"]
    API["FastAPI<br/>REST, SSE, metrics, OpenAPI<br/>token, session or OIDC auth"] --> DB
    API --> UI["Static web UI"]
    CHAT["Chat-ops bots<br/>stale-command guard, roles"] --> API
  end
  SCLIENT -->|outbound HTTPS only| SENTINEL["Sheltie Sentinel - off-site"]
```

### Deployment topology

The design treats three failure layers separately: the WAN link, power, and the agent host itself.

```mermaid
flowchart LR
  subgraph Home["Home or lab"]
    A1["sheltie-agent<br/>main server"]
    A2["sheltie-agent<br/>Raspberry Pi on UPS"]
    UPS["UPS via NUT"]
    UPS --> A1
    UPS --> A2
    A1 <-->|"peer heartbeats on LAN"| A2
    LAN["LAN-only channel<br/>ntfy or Home Assistant"]
    A1 --> LAN
    A2 --> LAN
  end
  subgraph Offsite["Off-site, free tier"]
    S["Sheltie Sentinel<br/>Cloudflare Worker, fly.io or VPS<br/>or healthchecks.io and Uptime Kuma push"]
  end
  A1 -->|"heartbeat and snapshot"| S
  A2 -->|"heartbeat and snapshot"| S
  S -->|"home went dark at 10:02, UPS was at 14%"| PHONE["Phone<br/>Telegram, ntfy, email"]
  A1 -->|"outbox flush and digest"| PHONE
```

### Outbox delivery

Every alert is written to the outbox in the same transaction that records it. Delivery happens afterwards and is retried until it succeeds.

```mermaid
stateDiagram-v2
  [*] --> pending: alert committed
  pending --> sending: dispatcher picks due row
  sending --> sent: 2xx
  sending --> pending: network error, 429 or 5xx - backoff
  pending --> superseded: resolved before delivery
  pending --> digested: backlog too large or too old
  sending --> failover: channel failing for too long
  failover --> pending: next channel in priority list
  sent --> [*]
  digested --> [*]
  superseded --> [*]
```

- Backoff is `min(5s * 2^attempts, 5m)` with jitter, and honours Telegram's `retry_after` on 429.
- When the backlog is more than N messages or older than T, the queue collapses into a single **"While you were offline"** digest.
- Alerts that fired and recovered before they could be delivered are reported in the digest as "flapped", not sent as two separate messages.

---

## Failure scenarios

### Long network disconnection

```mermaid
sequenceDiagram
  participant M as Monitors
  participant E as Alert engine
  participant O as Outbox in SQLite
  participant D as Dispatcher
  participant T as Telegram
  M->>E: WAN check - gateway ok, DNS fail, HTTPS fail
  E->>O: "Internet lost - ISP side" committed
  D->>T: send
  T--xD: connection error
  Note over D: retry 5s, 10s, 20s ... capped at 5m
  M->>E: container nextcloud died at 10:30
  E->>O: committed, auto-heal recovers it at 10:31
  M->>E: WAN restored at 12:15
  D->>O: backlog of 6 rows, oldest 2h13m old
  D->>T: one digest - internet down 10:02 to 12:15, nextcloud died and healed, disk 91% for 40m and recovered
  T-->>D: 200
  D->>O: rows marked digested
```

- **Dependencies:** the WAN monitor checks the gateway, then DNS, then HTTPS endpoints. While the WAN is down, dependent site alerts are muted and added to the digest instead of paging one by one.
- **LAN channel:** ntfy or Home Assistant on the LAN still reaches phones on home Wi-Fi when the ISP is down.
- **Stale commands:** a `/restart` sent during the outage is not executed hours later. *(Implemented.)*
- **Docker stream resume:** the agent persists the last event timestamp and reconnects with `since=`.

### Long power cut

```mermaid
sequenceDiagram
  participant U as UPS via NUT
  participant A as Agent
  participant DB as SQLite
  participant S as Sentinel
  participant P as Phone
  U->>A: on battery at 09:51
  A->>P: UPS on battery, 38 min runtime
  A->>DB: heartbeat every 30s
  A->>S: heartbeat and snapshot - UPS 14 percent
  Note over A,DB: power lost at 10:02, no clean-shutdown flag written
  S->>P: home went dark at 10:02, last snapshot UPS at 14 percent - probably a power cut
  Note over A: power returns, host boots at 13:47
  A->>DB: read last heartbeat 10:02, clean flag false, boot time changed
  A->>A: wait for NTP sync before computing the downtime
  A->>P: probable power loss, down 10:02 to 13:47 - 3h45m
  A->>P: after 2 min boot grace - 23 of 25 containers running, immich_ml exited 137
```

How the boot classifier decides what happened:

| Same boot ID as last heartbeat? | Clean-shutdown flag | Verdict |
|---|---|---|
| yes | no | Agent crashed or was killed |
| no | yes | Planned host reboot |
| no | no | **Power loss or kernel crash** |

- **Clock sanity:** durations use the monotonic clock. Downtime is only computed after NTP sync; otherwise it is labelled approximate. This matters on Raspberry Pi boards that have no RTC.
- **Boot storm:** Docker events during the first two minutes after boot are aggregated into one summary instead of one message per container.

### Long server downtime

The agent cannot report its own death, so the watcher must live off the host:

1. **`heartbeat.urls`**: ping healthchecks.io, an Uptime Kuma push monitor or any similar URL. This works on day one.
2. **Sheltie Sentinel**: a small open-source receiver that stores the last snapshot, so a missed heartbeat produces a contextual alert ("last seen with WAN degraded and UPS at 14%").
3. **Peer mesh**: two agents on the same LAN watch each other and alert through their own channels.
4. **Self-health**: each internal task has a watchdog, and the Docker `HEALTHCHECK` reports watchdog state.

---

## Plugin interface (planned)

Plugins are discovered through Python entry points (`sheltie.monitors`, `sheltie.notifiers`, `sheltie.actions`), so a plugin can live in its own package or inside this repository.

```python
class Monitor(Protocol):
    kind: ClassVar[str]                    # "tls_expiry"
    Config: ClassVar[type[BaseModel]]      # pydantic schema, validated at startup

    async def check(self, ctx: CheckContext) -> list[Observation]: ...


@dataclass
class Observation:
    alert_id: str                          # "tls.example_com.expiring"
    active: bool                           # True = bad condition present
    severity: str                          # info | warning | critical | emergency
    title: str
    body: str
    metrics: dict[str, float]              # stored as time series
    depends_on: list[str] = field(default_factory=list)   # e.g. ["wan.down"]


class Notifier(Protocol):
    kind: ClassVar[str]
    async def send(self, message: Message) -> DeliveryResult: ...   # ok | retry_after | permanent_failure


class Action(Protocol):
    kind: ClassVar[str]
    destructive: ClassVar[bool]
    async def run(self, target: str, ctx: ActionContext) -> ActionResult: ...
```

Until this lands, new checks follow the existing `check_<name>(config, state, alerts)` pattern described in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Storage model (planned)

| Table | Purpose | Retention |
|---|---|---|
| `kv_state` | Current values and alert state (replaces `state.json`) | Forever |
| `events` | Alert, recovery, action and audit history | 90 days (configurable) |
| `metrics_raw` / `metrics_1m` / `metrics_1h` | Time series rollups | 24h / 7d / 90d |
| `outbox` | Pending and sent notifications with attempts and next-attempt time | 7 days after delivery |
| `lifecycle` | Heartbeat, boot ID, clean-shutdown flag | Last 100 boots |

SQLite runs in WAL mode with `synchronous=FULL`. Writes are batched into one transaction per check cycle to limit SD-card wear. On first start after upgrading, `state.json` is migrated and kept as `state.json.bak`.
