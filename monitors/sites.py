import logging
import time
from typing import Any

import requests


# Keyword checks only need the start of a page; never pull a huge download into memory.
MAX_BODY_BYTES = 1024 * 1024


def configured_sites(config: dict[str, Any], state: Any) -> list[dict[str, Any]]:
    config_sites = config.get("sites") or []
    runtime_sites = state.get("sites.custom", [])
    merged: dict[str, dict[str, Any]] = {}

    for site in config_sites + runtime_sites:
        if not isinstance(site, dict):
            continue
        key = str(site.get("name") or site.get("url") or "").lower()
        if key:
            merged[key] = site

    return list(merged.values())


def check_sites(config: dict[str, Any], state: Any, alerts: Any) -> None:
    sites = configured_sites(config, state)
    if not sites:
        state.set("sites.status", [])
        return

    results = []
    for site in sites:
        # One malformed entry (for example an old runtime site saved before validation)
        # must not stop every other site from being checked.
        try:
            result = check_site(site, state, alerts)
        except Exception:
            logging.exception("Skipping site monitor %r: invalid settings", site.get("name") or site.get("url"))
            continue
        if result is not None:
            results.append(result)

    state.set("sites.status", results)


def read_capped_text(response: Any, limit: int = MAX_BODY_BYTES) -> str:
    """Read at most `limit` bytes of a streamed response body."""
    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        chunks.append(chunk)
        size += len(chunk)
        if size >= limit:
            break
    body = b"".join(chunks)[:limit]
    return body.decode(response.encoding or "utf-8", errors="replace")


def probe_site(site: dict[str, Any]) -> dict[str, Any] | None:
    """Request one site and report what happened. No state, history or alerts."""
    name = str(site.get("name") or site.get("url") or "unnamed")
    url = str(site.get("url") or "")
    if not url:
        return None

    timeout = float(site.get("timeout", 10))
    expected_status = site.get("expected_status", [200])
    if isinstance(expected_status, int):
        expected_status = [expected_status]
    keyword = site.get("keyword")

    started = time.perf_counter()
    status_code = None
    latency_ms = None
    error = None
    up = False

    try:
        with requests.get(
            url,
            timeout=timeout,
            allow_redirects=bool(site.get("follow_redirects", True)),
            headers={"User-Agent": "Sheltie/1.0"},
            stream=True,
        ) as response:
            latency_ms = round((time.perf_counter() - started) * 1000)
            status_code = response.status_code
            up = status_code in expected_status
            if keyword:
                up = up and str(keyword) in read_capped_text(response)
    except requests.RequestException as exc:
        latency_ms = round((time.perf_counter() - started) * 1000)
        error = str(exc)

    return {
        "name": name,
        "url": url,
        "up": up,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "error": error,
        "expected_status": expected_status,
    }


def check_site(site: dict[str, Any], state: Any, alerts: Any) -> dict[str, Any] | None:
    result = probe_site(site)
    if result is None:
        return None

    name = result["name"]
    url = result["url"]
    up = result["up"]
    status_code = result["status_code"]
    latency_ms = result["latency_ms"]
    error = result["error"]
    expected_status = result["expected_status"]
    keyword = site.get("keyword")
    severity = site.get("severity", "critical")
    duration = site.get("duration", site.get("down_duration", 0))
    cooldown = site.get("cooldown")
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_") or "site"

    history_key = f"metrics.sites.{safe_name}.history"
    history = list(state.get(history_key, []))
    history.append(
        {
            "ts": int(time.time()),
            "up": up,
            "status_code": status_code,
            "latency_ms": latency_ms,
        }
    )
    history = history[-80:]
    result["history"] = history
    state.set(f"metrics.sites.{safe_name}.up", up)
    state.set(f"metrics.sites.{safe_name}.latency_ms", latency_ms)
    state.set(f"metrics.sites.{safe_name}.status_code", status_code)
    state.set(history_key, history)

    detail = [
        f"Site: {name}",
        f"URL: {url}",
        f"Expected: {', '.join(str(code) for code in expected_status)}",
        f"Status: {status_code if status_code is not None else 'none'}",
        f"Latency: {latency_ms if latency_ms is not None else 'unknown'}ms",
    ]
    if keyword:
        detail.append(f"Keyword: {keyword}")
    if error:
        detail.append(f"Error: {error}")

    alerts.condition(
        alert_id=f"site.{safe_name}.down",
        source="site",
        active=not up,
        severity=severity,
        title=f"Site down: {name}",
        alert_body="\n".join(detail),
        recovery_body="\n".join(detail),
        duration=duration,
        cooldown=cooldown,
    )
    return result
