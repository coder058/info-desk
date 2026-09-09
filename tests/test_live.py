"""SYNTHETIC fixtures and failures. No external HTTP or model calls in CI."""
import json
import time
from datetime import datetime, timedelta, timezone
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from infodesk.app import create_app
from infodesk.connectors import Connector, next_check, parse_feed, safe_document_url
from infodesk.live_service import LiveRequest, LiveService, validate_answer
from infodesk.live_store import LiveStore

SYNTHETIC_RSS = b'''<rss><channel><item><title>SYNTHETIC gas output</title>
<link>https://www.eia.gov/todayinenergy/detail.php?id=SYNTHETIC</link>
<description>SYNTHETIC gas output reached 12 units.</description>
<pubDate>Wed, 09 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>'''


def document(body="SYNTHETIC gas output reached 12 units.", url=None):
    return {"title": "SYNTHETIC gas report", "body": body, "published_at": "2026-09-09",
            "url": url or "https://www.eia.gov/todayinenergy/detail.php?id=SYNTHETIC",
            "coverage": "SYNTHETIC test document"}


def wait_job(store, job_id):
    # GUESS: bounded test wait, not a service latency measurement.
    for _ in range(200):
        result = store.job(job_id)
        if result["state"] not in {"queued", "running"}:
            return result
        time.sleep(.01)
    raise AssertionError("SYNTHETIC job did not complete")


def test_SYNTHETIC_live_ingestion_versions_and_latest_only_retrieval():
    store = LiveStore()
    try:
        first = store.ingest("eia", document())
        again = store.ingest("eia", document())
        revised = store.ingest("eia", document("SYNTHETIC gas output reached 14 units."))
        assert first["change"] == "new_to_desk" and again["change"] == "unchanged"
        assert first["version_id"] == again["version_id"]
        assert revised["change"] == "revised"
        versions = store.document(first["document_id"])["versions"]
        assert len(versions) == 2 and "12 units" in versions[1]["body"]
        hits = store.retrieve("gas output", ["eia"])
        assert hits and all(hit["version_id"] == revised["version_id"] for hit in hits)
        assert not store.retrieve("SYNTHETIC-unmatched", ["ofac-live"])
        assert not store.retrieve("gas", ["eia"], ["missing"])
        reverted = store.ingest("eia", document())
        assert reverted["change"] == "revised" and reverted["version_id"] != first["version_id"]
    finally:
        store.close()


def test_SYNTHETIC_retrieval_handles_query_operators_as_text():
    store = LiveStore()
    try:
        store.ingest("eia", document())
        assert isinstance(store.retrieve('" OR gas * NOT : )', ["eia"]), list)
        assert store.retrieve("the and what", ["eia"]) == []
    finally:
        store.close()


@pytest.mark.parametrize("url", ["https://127.0.0.1/private", "file:///etc/passwd", "https://www.eia.gov.evil.test/x", "https://user:pass@www.eia.gov/x", "https://www.eia.gov:8000/x"])
def test_SYNTHETIC_source_urls_cannot_escape_allowlist(url):
    with pytest.raises(ValueError):
        safe_document_url(url, "eia")


def test_SYNTHETIC_rss_and_json_parsers_preserve_scope():
    result = parse_feed("eia", SYNTHETIC_RSS)
    assert result[0]["published_at"] == "2026-09-09T12:00:00+00:00"
    assert "summaries" in result[0]["coverage"]
    data = {"results": [{"title": "SYNTHETIC notice", "abstract": None, "publication_date": "2026-09-09",
                         "html_url": "https://www.federalregister.gov/documents/SYNTHETIC"}]}
    assert "missing" in parse_feed("federal-register", json.dumps(data).encode())[0]["coverage"]


def test_SYNTHETIC_ofac_selector_ignores_unrelated_navigation():
    html = b'<main><p>SYNTHETIC navigation</p><ul><li><a>Venezuela General License 99S</a> - SYNTHETIC example</li></ul></main>'
    result = parse_feed("ofac-live", html)
    assert "navigation" not in result[0]["body"]
    assert result[0]["published_at"] is None


def test_SYNTHETIC_connector_error_and_retry_after_do_not_fake_success():
    store = LiveStore()
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})
    connector = Connector(store, httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        result = connector.refresh("eia")
        assert result["status"] == "error" and "429" in result["detail"]
        assert not store.documents()
        assert datetime.fromisoformat(result["check"]["next_check_at"]) > datetime.now(timezone.utc)+timedelta(seconds=110)
        assert connector.refresh("eia")["status"] == "cooldown" and len(calls) == 1
    finally:
        connector.close()
        store.close()


def test_SYNTHETIC_etag_304_reuses_version_and_sends_conditional_header():
    store = LiveStore()
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=SYNTHETIC_RSS, headers={"ETag": '"SYNTHETIC"'}) if len(requests)==1 else httpx.Response(304)
    connector = Connector(store, httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        connector.refresh("eia")
        store.conn.execute("UPDATE live_checks SET next_check_at='2000-01-01T00:00:00+00:00'")
        store.conn.commit()
        second = connector.refresh("eia")
        assert second["status"] == "unchanged"
        assert requests[1].headers["if-none-match"] == '"SYNTHETIC"'
        assert store.documents()[0]["version_count"] == 1
    finally:
        connector.close()
        store.close()


@pytest.mark.parametrize("content", [b'<html>SYNTHETIC blocked page</html>', b'<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///SYNTHETIC">]><rss><channel><item>&xxe;</item></channel></rss>'])
def test_SYNTHETIC_bad_rss_and_entities_are_visible_failures(content):
    store = LiveStore()
    connector = Connector(store, httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=content))))
    try:
        assert connector.refresh("eia")["status"] == "error"
        assert not store.documents()
    finally:
        connector.close()
        store.close()


def test_SYNTHETIC_cache_control_is_respected():
    assert datetime.fromisoformat(next_check({"cache-control":"public, max-age=300"})) > datetime.now(timezone.utc)+timedelta(seconds=290)


def passage():
    return [{"chunk_id": "SYNTHETIC:0", "body": "SYNTHETIC gas output reached 12 units."}]


def answer(text="Gas output reached 12 units.", chunk_id="SYNTHETIC:0", quote="gas output reached 12 units."):
    return {"statements":[{"text":text,"citations":[{"chunk_id":chunk_id,"quote":quote}]}],"insufficient_evidence":False}


@pytest.mark.parametrize("payload", [answer(chunk_id="invented"), answer(quote="made up evidence"), answer(text="Gas output reached 99 units."), {"statements":[],"insufficient_evidence":False}, {**answer(), "action":"publish"}])
def test_SYNTHETIC_bad_ai_answer_is_rejected(payload):
    with pytest.raises(ValueError):
        validate_answer(payload, passage())


def test_SYNTHETIC_valid_answer_and_abstention():
    assert validate_answer(answer(), passage())["statements"]
    assert validate_answer({"statements":[],"insufficient_evidence":True}, passage())["insufficient_evidence"]


def test_SYNTHETIC_year_context_adds_real_same_version_title_citation():
    passages = [
        {"chunk_id":"SYNTHETIC:title", "document_id":"SYNTHETIC", "version_id":1,
         "title":"SYNTHETIC gas report for 2026", "body":"SYNTHETIC gas report for 2026"},
        {**passage()[0], "document_id":"SYNTHETIC", "version_id":1},
    ]
    result = validate_answer(answer(text="Gas output reached 12 units in 2026."), passages)
    assert len(result["statements"][0]["citations"]) == 2
    assert result["citation_context_added"][0]["chunk_id"] == "SYNTHETIC:title"
    passages[0]["version_id"] = 2
    with pytest.raises(ValueError):
        validate_answer(answer(text="Gas output reached 12 units in 2026."), passages)
    with pytest.raises(ValueError):
        validate_answer(answer(text="Gas output reached 99 units in 2026."), passages)


class SyntheticConnector:
    def __init__(self, store):
        self.store = store
    def refresh(self, source_id):
        self.store.ingest(source_id, document())
        return {"source_id":source_id,"check":{"status":"ok"},"changes":[]}
    def close(self):
        pass


def test_SYNTHETIC_live_job_abstains_without_calling_model():
    store = LiveStore()
    def forbidden(*args):
        raise AssertionError("Model should not be called without evidence")
    service = LiveService(store, SyntheticConnector(store), forbidden)
    try:
        job = service.submit("ask", LiveRequest(source_ids=["eia"],question="unicorns"))
        result = wait_job(store, job["id"])
        assert result["state"] == "completed"
        assert result["result"]["answer"]["insufficient_evidence"]
    finally:
        service.close()
        store.close()


def test_SYNTHETIC_model_failure_retains_passages_and_failed_state():
    store = LiveStore()
    def fail(*args):
        raise TimeoutError("SYNTHETIC model timeout")
    service = LiveService(store, SyntheticConnector(store), fail)
    try:
        job = service.submit("ask", LiveRequest(source_ids=["eia"],question="gas output"))
        result = wait_job(store, job["id"])
        assert result["state"] == "failed" and result["result"]["passages"]
        assert result["result"]["answer"] is None and "timeout" in result["error"]
        assert not store.note_count()
    finally:
        service.close()
        store.close()


def test_SYNTHETIC_cancellation_and_backpressure():
    store = LiveStore()
    entered, release = Event(), Event()
    def blocking(*args):
        entered.set()
        assert release.wait(5)
        return answer()
    service = LiveService(store, SyntheticConnector(store), blocking)
    try:
        request = LiveRequest(source_ids=["eia"],question="gas output")
        job = service.submit("ask", request)
        assert entered.wait(5)
        with pytest.raises(RuntimeError):
            service.submit("ask", request)
        assert store.cancel_job(job["id"])
        release.set()
        service.active.result(timeout=5)
        assert store.job(job["id"])["state"] == "cancelled"
        assert store.job(job["id"])["result"] is None
    finally:
        release.set()
        service.close()
        store.close()


def test_SYNTHETIC_restart_marks_unfinished_jobs_interrupted(tmp_path):
    path = tmp_path/"SYNTHETIC-live.sqlite3"
    store = LiveStore(path)
    job = store.new_job("ask", {"question":"SYNTHETIC"})
    store.close()
    store = LiveStore(path)
    service = LiveService(store, SyntheticConnector(store))
    try:
        assert store.job(job)["state"] == "interrupted"
    finally:
        service.close()
        store.close()


def test_SYNTHETIC_api_contract_and_document_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(Connector,"refresh",lambda self,sid:SyntheticConnector(self.store).refresh(sid))
    with TestClient(create_app(tmp_path/"SYNTHETIC-api.sqlite3")) as client:
        assert client.get("/api/live/status").json()["documents"] == []
        response = client.post("/api/live/ask",json={"source_ids":["eia"],"question":"gas output","use_model":False})
        assert response.status_code == 202
        job = wait_job(client.app.state.store,response.json()["id"])
        assert job["state"] == "completed" and job["result"]["passages"]
        doc = client.get("/api/live/status").json()["documents"][0]
        assert client.get(f'/api/live/documents/{doc["id"]}').json()["diff"] is None
        client.app.state.store.ingest("eia",document("SYNTHETIC gas output reached 14 units."))
        diff = client.get(f'/api/live/documents/{doc["id"]}').json()["diff"]
        assert "-SYNTHETIC gas output reached 12 units." in diff
        assert "+SYNTHETIC gas output reached 14 units." in diff
        assert client.get("/api/live/jobs/missing").status_code==404
        assert client.post("/api/live/sync",json={"source_ids":["eia","eia"]}).status_code==422
        assert client.post("/api/live/ask",json={"source_ids":["eia"],"question":""}).status_code==422
