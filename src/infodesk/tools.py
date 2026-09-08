from __future__ import annotations

from datetime import datetime, timezone

from .fixtures import LICENSES, SOURCES
from .schema import FetchRecord, Label


class FetchError(Exception):
    def __init__(self, status: int, source_id: str) -> None:
        super().__init__(f"fetch {source_id} returned {status}")
        self.status = status
        self.source_id = source_id


class SourceTools:
    """The only tools the desk may call. No free-form write."""

    names = ("fetch_source", "lookup_license", "search_prior_notes")

    def __init__(self, store, fail_first: str | None = None) -> None:
        self.store = store
        self._fail_first = fail_first
        self._failed: set[str] = set()

    def fetch_source(self, source_id: str) -> FetchRecord:
        if source_id not in SOURCES:
            raise FetchError(404, source_id)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if self._fail_first == source_id and source_id not in self._failed:
            self._failed.add(source_id)
            self.store.record_fetch(source_id, 429, now)
            raise FetchError(429, source_id)
        spec = SOURCES[source_id]
        record = FetchRecord(
            source_id=source_id,
            status=200,
            fetched_at=now,
            body=spec["html"],
            url=spec["url"],
            label=spec["label"],  # type: ignore[arg-type]
        )
        self.store.record_fetch(source_id, 200, now)
        self.store.upsert_source(
            source_id, record.url, record.fetched_at, record.label, record.body
        )
        return record

    def lookup_license(self, code: str) -> dict | None:
        return LICENSES.get(code)

    def search_prior_notes(self, query: str) -> list[dict]:
        return self.store.search_notes(query)
