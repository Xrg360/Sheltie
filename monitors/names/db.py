"""SQLite storage for names. One connection, guarded by a lock; traffic is tiny.

`python -m monitors.names import` reads another database with these tables.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,              -- 'proxy' | 'device'
    target_host TEXT NOT NULL DEFAULT '',
    target_port INTEGER,
    scheme      TEXT NOT NULL DEFAULT 'http',
    websockets  INTEGER NOT NULL DEFAULT 1,
    source      TEXT NOT NULL DEFAULT '',   -- what was picked, e.g. 'container:sheltie'
    label       TEXT NOT NULL DEFAULT '',   -- human description of the target
    npm_kind    TEXT,                       -- 'proxy' | 'redirect'
    npm_id      INTEGER,
    sync_error  TEXT,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    created_by  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS npm_garbage (
    npm_kind TEXT NOT NULL,
    npm_id   INTEGER NOT NULL,
    PRIMARY KEY (npm_kind, npm_id)
);
"""


class Database:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, and far fewer fsyncs
            self._conn.executescript(SCHEMA)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.lock:
            return self._conn.execute(sql, tuple(params))

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self.lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self._conn.execute(sql, tuple(params)).fetchall()]

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
