import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from infodesk.app import create_app
from infodesk.harness import run_harness
from infodesk.interpret import ollama_propose
from infodesk.schema import Finding, Proposal
from infodesk.sources import SOURCES
from infodesk.store import Store
from infodesk.workbench import analyse, build_bundle


def test_bundle_contains_every_nonempty_selection_and_input_hash():
    bundle = build_bundle()
    assert len(bundle["selections"]) == 2 ** len(SOURCES) - 1
    for key, run in bundle["selections"].items():
        assert key == "+".join(run["source_ids"])
        assert run["model_status"] == "not_requested"
        assert run["db"]["approved_writes"] == 0
        for source in run["sources"]:
            assert source["sha256"] == hashlib.sha256(SOURCES[source["id"]]["body"].encode()).hexdigest()
            assert source["capture_note"]


def test_annotations_are_not_publisher_evidence():
    assert "This page lists general licenses." not in SOURCES["ofac"]["body"]
    assert "This page is a White House fact sheet" not in SOURCES["white-house"]["body"]
    assert "SOURCE:" not in SOURCES["ofac"]["body"]


@pytest.mark.parametrize("ids", [[], ["ofac", "ofac"], ["unregistered"]])
def test_invalid_selections(ids):
    store = Store()
    try:
        with pytest.raises(ValueError):
            analyse(ids, store)
        assert not store.snapshot()["drafts"]
    finally:
        store.close()


def test_ap_alone_does_not_invent_white_house_only_royalties():
    store = Store()
    try:
        result = analyse(["ap"], store)
        assert "$200" not in result["body"]
        assert "royalty" not in result["body"]
    finally:
        store.close()


def test_api_runs_in_worker_thread_and_persists(tmp_path):
    path = tmp_path / "SYNTHETIC-test-ledger.sqlite3"
    with TestClient(create_app(path)) as client:
        assert client.get("/api/health").json()["ok"]
        client.get("/api/desk").raise_for_status()
        assert client.get("/api/db").json()["drafts"] == []
        response = client.post("/api/analyses", json={"source_ids": ["ofac", "white-house", "ap"]})
        assert response.status_code == 200, response.text
        first = response.json()
        again = client.post("/api/analyses", json={"source_ids": ["ofac", "white-house", "ap"]}).json()
        assert first["draft_id"] == again["draft_id"]
        assert first["run_id"] != again["run_id"]
        assert client.post(f'/api/drafts/{first["draft_id"]}/decide', json={"decision": "approve"}).status_code == 409
        assert client.post(f'/api/drafts/{first["draft_id"]}/decide', json={"decision": "reject"}).status_code == 200
        assert client.post(f'/api/drafts/{first["draft_id"]}/decide', json={"decision": "reject"}).status_code == 409
        saved = client.get(f'/api/runs/{first["run_id"]}').json()
        assert saved["db"]["drafts"][0]["status"] == "pending"  # Historical snapshot, not silently rewritten.
    with TestClient(create_app(path)) as client:
        assert len(client.get("/api/runs").json()) == 2
        assert client.get("/api/db").json()["drafts"][0]["status"] == "rejected"


def test_api_rejects_unknown_duplicate_and_empty_sources(tmp_path):
    with TestClient(create_app(tmp_path / "SYNTHETIC.sqlite3")) as client:
        for ids in [[], ["ofac", "ofac"], ["https://internal.test"]]:
            assert client.post("/api/analyses", json={"source_ids": ids}).status_code == 422
        assert client.get("/api/db").json()["drafts"] == []
        assert client.get("/api/runs/missing").status_code == 404


def test_local_api_rejects_cross_origin_write_and_rebinding(tmp_path):
    with TestClient(create_app(tmp_path / "SYNTHETIC.sqlite3")) as client:
        assert client.post("/api/analyses", json={"source_ids": ["ofac"]}, headers={"Origin": "https://evil.test"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "evil.test"}).status_code == 400
        assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_model_unavailable_is_not_reported_as_ai_success(tmp_path, monkeypatch):
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    with TestClient(create_app(tmp_path / "SYNTHETIC.sqlite3")) as client:
        assert not client.get("/api/health").json()["model_available"]
        assert client.post("/api/analyses", json={"source_ids": ["ofac"], "use_model": True}).status_code == 503


def test_SYNTHETIC_approval_across_connections_is_exactly_once(tmp_path):
    path = tmp_path / "SYNTHETIC-concurrent.sqlite3"
    first, second = Store(path), Store(path)
    try:
        draft = first.insert_draft("SYNTHETIC", "publish_draft", "SYNTHETIC", "SYNTHETIC approved note", "test")
        with ThreadPoolExecutor() as pool:
            outcomes = list(pool.map(lambda s: s.approve(draft), [first, second]))
        assert sorted(outcomes) == [False, True]
        assert first.note_count() == first.approved_write_count() == 1
        assert not first.reject(draft)
    finally:
        first.close()
        second.close()


def test_SYNTHETIC_dedupe_does_not_reuse_different_policy_or_case():
    store = Store()
    try:
        eligible = store.insert_draft("SYNTHETIC-a", "publish_draft", "SYNTHETIC", "SYNTHETIC same body", "test")
        held = store.insert_draft("SYNTHETIC-a", "hold", "SYNTHETIC", "SYNTHETIC same body", "test")
        other = store.insert_draft("SYNTHETIC-b", "hold", "SYNTHETIC", "SYNTHETIC same body", "test")
        assert len({eligible, held, other}) == 3
        assert not store.approve(held)
    finally:
        store.close()


@pytest.mark.parametrize("payload", [{"action": "publish_draft", "body": "SYNTHETIC invented fact"}, [], {"finding_order": ["99"]}, {"finding_order": ["0", "0"]}, {"finding_order": [0, 1]}])
def test_SYNTHETIC_model_cannot_invent_or_promote(payload, monkeypatch):
    fallback = Proposal("hold", "SYNTHETIC", "SYNTHETIC", (Finding("scope_gap", "SYNTHETIC"), Finding("single_source", "SYNTHETIC")), "heuristic")
    monkeypatch.setattr("infodesk.interpret._ollama_generate", lambda prompt: (json.dumps(payload), 0))
    actual, _ = ollama_propose("SYNTHETIC", fallback)
    assert actual == fallback


def test_SYNTHETIC_model_receives_evidence_and_can_only_reorder(monkeypatch):
    captured = []
    def generate(prompt):
        captured.append(prompt)
        return '{"finding_order": ["1", "0"]}', 0
    monkeypatch.setattr("infodesk.interpret._ollama_generate", generate)
    fallback = Proposal("hold", "SYNTHETIC", "SYNTHETIC", (Finding("scope_gap", "SYNTHETIC scope"), Finding("single_source", "SYNTHETIC figure")), "heuristic")
    actual, _ = ollama_propose("SYNTHETIC task", fallback)
    assert "SYNTHETIC scope" in captured[0]
    assert actual.findings == tuple(reversed(fallback.findings))
    assert actual.action == fallback.action and actual.body == fallback.body


def test_SYNTHETIC_model_failure_reports_fallback(monkeypatch):
    def fail(prompt):
        raise TimeoutError("SYNTHETIC timeout")
    monkeypatch.setattr("infodesk.interpret._ollama_generate", fail)
    report = run_harness(use_ollama=True)
    assert report["interpreter"] == "heuristic"
    assert all(row["model_status"] == "fallback" for row in report["cases"])
