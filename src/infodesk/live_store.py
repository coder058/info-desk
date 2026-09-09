"""Append-only document versions and durable checkpoints for the live desk."""
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from .store import Store, serialized


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class LiveStore(Store):
    def __init__(self, path=":memory:"):
        super().__init__(path)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS live_documents (
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL, url TEXT NOT NULL,
                title TEXT NOT NULL, published_at TEXT, first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL, latest_version INTEGER
            );
            CREATE TABLE IF NOT EXISTS live_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL,
                title TEXT NOT NULL, body TEXT NOT NULL, text_hash TEXT NOT NULL,
                received_at TEXT NOT NULL, published_at TEXT, coverage TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_chunks (
                id TEXT PRIMARY KEY, document_id TEXT NOT NULL, version_id INTEGER NOT NULL,
                body TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS live_fts USING fts5(chunk_id UNINDEXED, title, body);
            CREATE TABLE IF NOT EXISTS live_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL,
                checked_at TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL,
                duration_ms REAL NOT NULL, next_check_at TEXT NOT NULL,
                etag TEXT, last_modified TEXT
            );
            CREATE TABLE IF NOT EXISTS live_jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                request TEXT NOT NULL, trace TEXT NOT NULL, result TEXT, error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS versions_document ON live_versions(document_id, id);
            CREATE INDEX IF NOT EXISTS checks_source ON live_checks(source_id, id);
        """)
        self.conn.commit()

    @serialized
    def ingest(self, source_id, document):
        now = utcnow()
        doc_id = hashlib.sha256(document["url"].encode()).hexdigest()
        digest = hashlib.sha256(json.dumps({k: document.get(k) for k in
            ("title", "body", "published_at", "coverage")}, sort_keys=True).encode()).hexdigest()
        with self.conn:
            previous = self.conn.execute("""SELECT v.* FROM live_documents d
                JOIN live_versions v ON d.latest_version=v.id WHERE d.id=?""", (doc_id,)).fetchone()
            if previous and previous["text_hash"] == digest:
                self.conn.execute("UPDATE live_documents SET last_seen=? WHERE id=?", (now, doc_id))
                return {"document_id": doc_id, "change": "unchanged", "version_id": previous["id"]}
            self.conn.execute("""INSERT INTO live_documents
                (id, source_id, url, title, published_at, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                    published_at=excluded.published_at, last_seen=excluded.last_seen""",
                (doc_id, source_id, document["url"], document["title"], document.get("published_at"), now, now))
            cur = self.conn.execute("""INSERT INTO live_versions
                (document_id, title, body, text_hash, received_at, published_at, coverage)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (doc_id, document["title"], document["body"],
                digest, now, document.get("published_at"), document["coverage"]))
            version_id = cur.lastrowid
            self.conn.execute("UPDATE live_documents SET latest_version=? WHERE id=?", (version_id, doc_id))
            # GUESS: passage size is a context/resource budget, not a calibrated retrieval optimum.
            # Keep paragraph boundaries where possible, then bound unusually long paragraphs.
            paragraphs = [p.strip() for p in document["body"].split("\n") if p.strip()]
            pieces = []
            for paragraph in paragraphs:
                words = paragraph.split()
                pieces.extend(" ".join(words[start:start + 160]) for start in range(0, len(words), 160))
            for index, body in enumerate(pieces):
                chunk_id = f"{version_id}:{index}"
                self.conn.execute("INSERT INTO live_chunks VALUES (?, ?, ?, ?)", (chunk_id, doc_id, version_id, body))
                self.conn.execute("INSERT INTO live_fts VALUES (?, ?, ?)", (chunk_id, document["title"], body))
        return {"document_id": doc_id, "change": "revised" if previous else "new_to_desk", "version_id": version_id}

    @serialized
    def add_check(self, source_id, status, detail, duration_ms, next_check_at, etag=None, last_modified=None):
        with self.conn:
            self.conn.execute("""INSERT INTO live_checks
                (source_id, checked_at, status, detail, duration_ms, next_check_at, etag, last_modified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (source_id, utcnow(), status, detail,
                duration_ms, next_check_at, etag, last_modified))

    @serialized
    def latest_checks(self):
        rows = self.conn.execute("""SELECT * FROM live_checks WHERE id IN
            (SELECT MAX(id) FROM live_checks GROUP BY source_id)""").fetchall()
        return {row["source_id"]: dict(row) for row in rows}

    @serialized
    def documents(self):
        return [dict(row) for row in self.conn.execute("""SELECT d.*, v.coverage, v.text_hash,
            (SELECT COUNT(*) FROM live_versions WHERE document_id=d.id) AS version_count
            FROM live_documents d JOIN live_versions v ON v.id=d.latest_version
            ORDER BY COALESCE(d.published_at, d.first_seen) DESC, d.id""").fetchall()]

    @serialized
    def document(self, doc_id):
        row = self.conn.execute("SELECT * FROM live_documents WHERE id=?", (doc_id,)).fetchone()
        if not row:
            return None
        versions = [dict(v) for v in self.conn.execute("SELECT * FROM live_versions WHERE document_id=? ORDER BY id DESC", (doc_id,)).fetchall()]
        return {**dict(row), "versions": versions}

    @serialized
    def retrieve(self, question, source_ids, document_ids=()):
        stop = {"the", "and", "what", "which", "are", "does", "that", "from", "with", "about", "this", "have", "has", "for", "las", "los", "que", "una", "con", "del", "hay", "para", "como"}
        tokens = list(dict.fromkeys(word.lower() for word in re.findall(r"[^\W_]+", question, re.UNICODE) if len(word)>2 and word.lower() not in stop))
        if not tokens:
            return []
        match = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        params = [match, *source_ids]
        where = ""
        if document_ids:
            where = " AND d.id IN (" + ",".join("?" for _ in document_ids) + ")"
            params.extend(document_ids)
        # GUESS: six passages bound CPU-model context. Relevance is not calibrated.
        return [dict(row) for row in self.conn.execute("""SELECT c.id AS chunk_id, c.body,
            c.version_id, d.id AS document_id, d.source_id, d.url, d.title,
            v.received_at, v.published_at, v.text_hash, v.coverage, bm25(live_fts) AS rank
            FROM live_fts JOIN live_chunks c ON c.id=live_fts.chunk_id
            JOIN live_documents d ON d.id=c.document_id AND d.latest_version=c.version_id
            JOIN live_versions v ON v.id=c.version_id
            WHERE live_fts MATCH ? AND d.source_id IN (""" + ",".join("?" for _ in source_ids) + ")"
            + where + " ORDER BY rank, c.id LIMIT 6", params).fetchall()]

    @serialized
    def new_job(self, kind, request):
        job_id = uuid4().hex
        now = utcnow()
        with self.conn:
            self.conn.execute("INSERT INTO live_jobs VALUES (?, ?, 'queued', ?, '[]', NULL, NULL, ?, ?)",
                              (job_id, kind, json.dumps(request), now, now))
        return job_id

    @serialized
    def job(self, job_id):
        row = self.conn.execute("SELECT * FROM live_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        for field in ("request", "trace", "result"):
            data[field] = json.loads(data[field]) if data[field] is not None else None
        return data

    @serialized
    def job_step(self, job_id, step, duration_ms=None):
        job = self.job(job_id)
        if job["state"] == "cancelled":
            raise InterruptedError("Job cancelled")
        trace = job["trace"] + [{"step": step, "at": utcnow(), "duration_ms": duration_ms}]
        with self.conn:
            self.conn.execute("UPDATE live_jobs SET state='running', trace=?, updated_at=? WHERE id=?",
                              (json.dumps(trace), utcnow(), job_id))

    @serialized
    def finish_job(self, job_id, state, result=None, error=None):
        with self.conn:
            self.conn.execute("""UPDATE live_jobs SET state=?, result=?, error=?, updated_at=?
                WHERE id=? AND state!='cancelled'""", (state, json.dumps(result) if result is not None else None,
                error, utcnow(), job_id))

    @serialized
    def cancel_job(self, job_id):
        with self.conn:
            return self.conn.execute("""UPDATE live_jobs SET state='cancelled', updated_at=?
                WHERE id=? AND state IN ('queued','running')""", (utcnow(), job_id)).rowcount > 0

    @serialized
    def recover_jobs(self):
        with self.conn:
            self.conn.execute("""UPDATE live_jobs SET state='interrupted',
                error='Server restarted before completion; retry the request.', updated_at=?
                WHERE state IN ('queued','running')""", (utcnow(),))

    @serialized
    def recent_jobs(self):
        # GUESS: bounded history-page size, not a retention policy. No jobs are deleted.
        return [dict(row) for row in self.conn.execute("""SELECT id, kind, state, created_at, updated_at
            FROM live_jobs ORDER BY rowid DESC LIMIT 30""").fetchall()]
