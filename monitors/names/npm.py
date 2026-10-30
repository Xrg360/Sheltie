"""Minimal client for the Nginx Proxy Manager API.

Sheltie logs in as a dedicated NPM user that can only see the hosts it created,
so it never touches entries made by hand in NPM.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

PATHS = {
    "proxy": "/api/nginx/proxy-hosts",
    "redirect": "/api/nginx/redirection-hosts",
    "access": "/api/nginx/access-lists",
}


class NpmError(Exception):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class Npm:
    def __init__(self, url: str, email: str, password: str) -> None:
        self.url = url
        self.email = email
        self.password = password
        self._lock = threading.Lock()
        self._token: tuple[str, float] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.url and self.email and self.password)

    def _raw(self, method: str, path: str, body: Any = None, token: str | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()
            message = f"HTTP {exc.code}"
            try:
                message = json.loads(detail)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            raise NpmError(message, exc.code) from exc
        except urllib.error.URLError as exc:
            raise NpmError(f"Can't reach Nginx Proxy Manager at {self.url} ({exc.reason})") from exc
        except OSError as exc:
            raise NpmError(f"Can't reach Nginx Proxy Manager at {self.url} ({exc})") from exc
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return text.decode(errors="replace")

    def _token_value(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token[1] - 300:
                return self._token[0]
        if not self.configured:
            raise NpmError("Nginx Proxy Manager login isn't set (SHELTIE_NAMES_NPM_EMAIL / SHELTIE_NAMES_NPM_PASSWORD).")
        res = self._raw("POST", "/api/tokens", {"identity": self.email, "secret": self.password})
        if isinstance(res, dict) and res.get("requires_2fa"):
            raise NpmError("The Nginx Proxy Manager user for names has 2FA on. Use a dedicated user without 2FA.")
        token = res["token"]
        try:
            expires = datetime.fromisoformat(res["expires"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            expires = time.time() + 3600
        with self._lock:
            self._token = (token, expires)
        return token

    def request(self, method: str, path: str, body: Any = None) -> Any:
        token = self._token_value()
        try:
            return self._raw(method, path, body, token)
        except NpmError as exc:
            if exc.status != 401:
                raise
            with self._lock:
                self._token = None
            return self._raw(method, path, body, self._token_value())

    # --- typed helpers -------------------------------------------------------

    def me(self) -> dict[str, Any]:
        return self.request("GET", "/api/users/me?expand=permissions")

    def version(self) -> str:
        res = self._raw("GET", "/api/")
        v = (res or {}).get("version") or {}
        return f"{v.get('major', '?')}.{v.get('minor', '?')}.{v.get('revision', '?')}"

    def get(self, kind: str, item_id: int) -> dict[str, Any] | None:
        try:
            return self.request("GET", f"{PATHS[kind]}/{item_id}")
        except NpmError as exc:
            if exc.status in (403, 404):
                return None
            raise

    def create(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", PATHS[kind], body)

    def update(self, kind: str, item_id: int, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("PUT", f"{PATHS[kind]}/{item_id}", body)

    def delete(self, kind: str, item_id: int) -> None:
        try:
            self.request("DELETE", f"{PATHS[kind]}/{item_id}")
        except NpmError as exc:
            if exc.status != 404:
                raise
