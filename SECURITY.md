# Security policy

Sheltie runs with access to the Docker socket and, in the default Compose file, with `privileged: true` and host networking. A vulnerability in Sheltie can therefore mean root on the host, so please report problems privately.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/xrg360/sheltie/security/advisories/new). Please do not open a public issue for security problems.

Include the affected version or image tag, how to reproduce the problem, and the impact you expect. You should get an acknowledgement within 7 days.

## Supported versions

Only the latest release receives security fixes while the project is pre-1.0.

## Hardening recommendations

- Set `SHELTIE_ACTION_TOKEN` to a long random value. If you do not set one, Sheltie generates one on first start, logs it once, and stores it in `state/state.json`. Action endpoints always require a token.
- Do not expose ports `8710` or `8711` to the internet. Put them behind a reverse proxy with authentication or a VPN.
- Read-only endpoints (`/api/status`, `/metrics`, ...) are currently unauthenticated and reveal container names and network details.
- Set `actions.enabled: false` if you only want monitoring and no remote repairs.
- Keep `sheltie` in `actions.blocked_containers`.
