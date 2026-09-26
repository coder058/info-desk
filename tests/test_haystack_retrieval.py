"""SYNTHETIC checks that live retrieval actually runs Haystack, not a stub."""
import pytest
from haystack import Document, Pipeline
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever

from infodesk import haystack_retrieval as hr
from infodesk.live_store import LiveStore
from infodesk.haystack_retrieval import documents_from_captures, retrieve_passages


def capture(chunk_id, body, title="SYNTHETIC gas report", source_id="eia"):
    return {
        "chunk_id": chunk_id,
        "body": body,
        "version_id": int(str(chunk_id).split(":")[0]),
        "document_id": f"doc-{chunk_id}",
        "source_id": source_id,
        "url": "https://www.eia.gov/todayinenergy/detail.php?id=SYNTHETIC",
        "title": title,
        "received_at": "2026-09-09T12:00:00+00:00",
        "published_at": "2026-09-09",
        "text_hash": "SYNTHETIC",
        "coverage": "SYNTHETIC test document",
    }


def test_production_module_imports_haystack_pipeline():
    assert hr.Document is Document
    assert hr.Pipeline is Pipeline
    assert hr.InMemoryBM25Retriever is InMemoryBM25Retriever
    docs = documents_from_captures([capture("1:0", "SYNTHETIC gas output reached 12 units.")])
    assert len(docs) == 1 and isinstance(docs[0], Document)
    assert docs[0].meta["body"] == "SYNTHETIC gas output reached 12 units."


def test_SYNTHETIC_haystack_pipeline_ranks_matching_passage(monkeypatch):
    ran = {}
    original = Pipeline.run

    def wrapped(self, *args, **kwargs):
        ran["used"] = True
        return original(self, *args, **kwargs)

    monkeypatch.setattr(hr.Pipeline, "run", wrapped)
    rows = [
        capture("1:0", "SYNTHETIC gas output reached 12 units.", title="gas report"),
        capture("2:0", "Unrelated license titles only.", title="licenses", source_id="ofac-live"),
    ]
    hits = retrieve_passages("gas output", rows)
    assert ran.get("used") is True
    assert hits and hits[0]["chunk_id"] == "1:0"
    assert "gas output" in hits[0]["body"]
    assert retrieve_passages("unicorns", rows) == []


def test_SYNTHETIC_retrieve_uses_haystack_not_sqlite_fts(monkeypatch):
    store = LiveStore()
    try:
        store.ingest("eia", {
            "title": "SYNTHETIC gas report",
            "body": "SYNTHETIC gas output reached 12 units.",
            "published_at": "2026-09-09",
            "url": "https://www.eia.gov/todayinenergy/detail.php?id=SYNTHETIC",
            "coverage": "SYNTHETIC test document",
        })
        # FTS5 still has the capture. If retrieve() were still MATCH-based,
        # stubbing Haystack would still return the gas passage.
        monkeypatch.setattr("infodesk.live_store.retrieve_passages",
                            lambda *args, **kwargs: [{
                                "chunk_id": "haystack-sentinel",
                                "body": "Haystack sentinel passage",
                                "version_id": 1,
                                "document_id": "sentinel",
                                "source_id": "eia",
                                "url": "https://www.eia.gov/todayinenergy/detail.php?id=SYNTHETIC",
                                "title": "sentinel",
                                "received_at": "t",
                                "published_at": "p",
                                "text_hash": "h",
                                "coverage": "c",
                                "rank": 1.0,
                            }])
        hits = store.retrieve("gas output", ["eia"])
        assert hits == [{"chunk_id": "haystack-sentinel", "body": "Haystack sentinel passage",
                         "version_id": 1, "document_id": "sentinel", "source_id": "eia",
                         "url": "https://www.eia.gov/todayinenergy/detail.php?id=SYNTHETIC",
                         "title": "sentinel", "received_at": "t", "published_at": "p",
                         "text_hash": "h", "coverage": "c", "rank": 1.0}]
        monkeypatch.setattr("infodesk.live_store.retrieve_passages",
                            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Haystack step removed")))
        with pytest.raises(RuntimeError, match="Haystack step removed"):
            store.retrieve("gas output", ["eia"])
    finally:
        store.close()
