from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from .schema import Label


class Store:
    """SQLite is the only writer. The interpreter has no insert method."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                label TEXT NOT NULL,
                body_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fetches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                status INTEGER NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                action TEXT NOT NULL,
                headline TEXT NOT NULL,
                body TEXT NOT NULL,
                body_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                interpreter TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id INTEGER NOT NULL UNIQUE,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()

    def upsert_source(self, source_id: str, url: str, fetched_at: str, label: Label, body: str) -> None:
        digest = hashlib.sha256(body.encode()).hexdigest()
        self.conn.execute(
            """
            INSERT INTO sources (source_id, url, fetched_at, label, body_hash)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                fetched_at=excluded.fetched_at, body_hash=excluded.body_hash
            """,
            (source_id, url, fetched_at, label, digest),
        )
        self.conn.commit()

    def record_fetch(self, source_id: str, status: int, fetched_at: str) -> None:
        self.conn.execute(
            "INSERT INTO fetches (source_id, status, fetched_at) VALUES (?, ?, ?)",
            (source_id, status, fetched_at),
        )
        self.conn.commit()

    def fetches(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT source_id, status FROM fetches ORDER BY id"
        ).fetchall()
        return [(row["source_id"], int(row["status"])) for row in rows]

    def has_duplicate_draft(self, body_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM drafts WHERE body_hash=? LIMIT 1", (body_hash,)
        ).fetchone()
        return row is not None

    def insert_draft(
        self, case_id: str, action: str, headline: str, body: str, interpreter: str
    ) -> int:
        digest = hashlib.sha256(body.encode()).hexdigest()
        if self.has_duplicate_draft(digest):
            existing = self.conn.execute(
                "SELECT id FROM drafts WHERE body_hash=? ORDER BY id DESC LIMIT 1",
                (digest,),
            ).fetchone()
            return int(existing["id"])
        cur = self.conn.execute(
            """
            INSERT INTO drafts (case_id, action, headline, body, body_hash, status, interpreter)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (case_id, action, headline, body, digest, interpreter),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def approve(self, draft_id: int) -> bool:
        row = self.conn.execute(
            "SELECT action, status, body FROM drafts WHERE id=?", (draft_id,)
        ).fetchone()
        if row is None or row["status"] != "pending":
            return False
        if row["action"] != "publish_draft":
            return False
        self.conn.execute(
            "UPDATE drafts SET status='approved' WHERE id=?", (draft_id,)
        )
        self.conn.execute(
            "INSERT INTO approvals (draft_id, decision) VALUES (?, 'approved')",
            (draft_id,),
        )
        self.conn.execute(
            "INSERT INTO notes (draft_id, body) VALUES (?, ?)",
            (draft_id, row["body"]),
        )
        self.conn.commit()
        return True

    def reject(self, draft_id: int) -> bool:
        row = self.conn.execute(
            "SELECT status FROM drafts WHERE id=?", (draft_id,)
        ).fetchone()
        if row is None or row["status"] != "pending":
            return False
        self.conn.execute(
            "UPDATE drafts SET status='rejected' WHERE id=?", (draft_id,)
        )
        self.conn.execute(
            "INSERT INTO approvals (draft_id, decision) VALUES (?, 'rejected')",
            (draft_id,),
        )
        self.conn.commit()
        return True

    def note_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0])

    def approved_write_count(self) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM approvals WHERE decision='approved'"
            ).fetchone()[0]
        )

    def search_notes(self, query: str) -> list[dict]:
        like = f"%{query}%"
        rows = self.conn.execute(
            "SELECT id, body FROM notes WHERE body LIKE ? ORDER BY id", (like,)
        ).fetchall()
        return [{"id": int(row["id"]), "body": row["body"]} for row in rows]

    def snapshot(self) -> dict:
        return {
            "notes": self.note_count(),
            "approved_writes": self.approved_write_count(),
            "drafts": [
                dict(row)
                for row in self.conn.execute(
                    "SELECT id, case_id, action, status FROM drafts ORDER BY id"
                ).fetchall()
            ],
            "fetches": self.fetches(),
        }

    def close(self) -> None:
        self.conn.close()
