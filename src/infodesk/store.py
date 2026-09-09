from __future__ import annotations

import hashlib
import json
import sqlite3
from functools import wraps
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .schema import Label


def serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call


class Store:
    """Thread-safe local store. Conditional approval and note writes are atomic."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = RLock()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY, url TEXT NOT NULL, fetched_at TEXT NOT NULL,
                label TEXT NOT NULL, body_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fetches (
                id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL,
                status INTEGER NOT NULL, fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
                action TEXT NOT NULL, headline TEXT NOT NULL, body TEXT NOT NULL,
                body_hash TEXT NOT NULL, status TEXT NOT NULL, interpreter TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS draft_identity
                ON drafts(case_id, action, headline, body_hash, interpreter);
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id INTEGER NOT NULL UNIQUE,
                body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id INTEGER NOT NULL,
                decision TEXT NOT NULL, at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL, payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    @serialized
    def upsert_source(self, source_id: str, url: str, fetched_at: str, label: Label, body: str) -> None:
        # Latest-source index only. Run payloads retain the hash for each analysis.
        with self.conn:
            self.conn.execute("""
                INSERT INTO sources VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET url=excluded.url,
                    fetched_at=excluded.fetched_at, label=excluded.label,
                    body_hash=excluded.body_hash
            """, (source_id, url, fetched_at, label, hashlib.sha256(body.encode()).hexdigest()))

    @serialized
    def record_fetch(self, source_id: str, status: int, fetched_at: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO fetches (source_id, status, fetched_at) VALUES (?, ?, ?)",
                              (source_id, status, fetched_at))

    @serialized
    def fetches(self) -> list[tuple[str, int]]:
        return [(row["source_id"], int(row["status"])) for row in
                self.conn.execute("SELECT source_id, status FROM fetches ORDER BY id").fetchall()]

    @serialized
    def has_duplicate_draft(self, body_hash: str) -> bool:
        return self.conn.execute("SELECT 1 FROM drafts WHERE body_hash=? LIMIT 1", (body_hash,)).fetchone() is not None

    @serialized
    def insert_draft(self, case_id: str, action: str, headline: str, body: str, interpreter: str) -> int:
        if action not in {"publish_draft", "hold", "verify_first"}:
            raise ValueError("unknown draft action")
        identity = (case_id, action, headline, hashlib.sha256(body.encode()).hexdigest(), interpreter)
        with self.conn:
            self.conn.execute("""
                INSERT INTO drafts (case_id, action, headline, body_hash, interpreter, body, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                ON CONFLICT(case_id, action, headline, body_hash, interpreter) DO NOTHING
            """, (*identity, body))
            row = self.conn.execute("""
                SELECT id FROM drafts WHERE case_id=? AND action=? AND headline=? AND body_hash=? AND interpreter=?
            """, identity).fetchone()
        return int(row["id"])

    @serialized
    def approve(self, draft_id: int) -> bool:
        with self.conn:
            changed = self.conn.execute("""
                UPDATE drafts SET status='approved'
                WHERE id=? AND status='pending' AND action='publish_draft'
            """, (draft_id,)).rowcount
            if not changed:
                return False
            self.conn.execute("INSERT INTO approvals (draft_id, decision) VALUES (?, 'approved')", (draft_id,))
            self.conn.execute("INSERT INTO notes (draft_id, body) SELECT id, body FROM drafts WHERE id=?", (draft_id,))
        return True

    @serialized
    def reject(self, draft_id: int) -> bool:
        with self.conn:
            changed = self.conn.execute("UPDATE drafts SET status='rejected' WHERE id=? AND status='pending'", (draft_id,)).rowcount
            if not changed:
                return False
            self.conn.execute("INSERT INTO approvals (draft_id, decision) VALUES (?, 'rejected')", (draft_id,))
        return True

    @serialized
    def note_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0])

    @serialized
    def approved_write_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM approvals WHERE decision='approved'").fetchone()[0])

    @serialized
    def search_notes(self, query: str) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT id, body FROM notes WHERE body LIKE ? ORDER BY id", (f"%{query}%",)).fetchall()]

    @serialized
    def snapshot(self) -> dict:
        return {
            "notes": self.note_count(), "approved_writes": self.approved_write_count(),
            "drafts": [dict(row) for row in self.conn.execute("SELECT id, case_id, action, status FROM drafts ORDER BY id").fetchall()],
            "fetches": self.fetches(),
            "approvals": [dict(row) for row in self.conn.execute("SELECT draft_id, decision, at FROM approvals ORDER BY id").fetchall()],
        }

    @serialized
    def save_run(self, case_id: str, payload: dict) -> str:
        run_id = uuid4().hex
        with self.conn:
            self.conn.execute("INSERT INTO runs (id, case_id, payload) VALUES (?, ?, ?)",
                              (run_id, case_id, json.dumps(payload)))
        return run_id

    @serialized
    def get_run(self, run_id: str) -> dict | None:
        row = self.conn.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        return {**json.loads(row["payload"]), "run_id": run_id} if row else None

    @serialized
    def list_runs(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT id, case_id, created_at FROM runs ORDER BY rowid DESC").fetchall()]

    @serialized
    def close(self) -> None:
        self.conn.close()
