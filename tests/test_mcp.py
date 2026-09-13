"""SYNTHETIC MCP checks. No external HTTP or model calls in CI."""
import asyncio
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from mcp import Client, StdioServerParameters

from infodesk.app import create_app
from infodesk.live_store import LiveStore
from infodesk.mcp_server import desk_mcp
from infodesk.mcp_tools import ToolError, bind_store, call_tool, list_tools
from infodesk.sources import ROOT


def live_document(body="SYNTHETIC gas output reached 12 units."):
    return {"title": "SYNTHETIC gas report", "body": body, "published_at": "2026-09-09",
            "url": "https://www.eia.gov/todayinenergy/detail.php?id=SYNTHETIC",
            "coverage": "SYNTHETIC test document"}


def seed_live(store):
    store.ingest("eia", live_document())
    store.add_check("eia", "error", "429 Too Many Requests", 12, "2026-09-09T12:02:00+00:00")
    store.add_check("federal-register", "error", "ReadTimeout: SYNTHETIC connector timeout", 15,
                    "2026-09-09T12:02:00+00:00")


def test_SYNTHETIC_each_mcp_tool_is_invoked_and_propose_write_needs_approve():
    store = LiveStore()
    try:
        seed_live(store)
        names = {item["name"] for item in list_tools()}
        assert names == {"search_sources", "get_claim", "propose_write"}

        found = call_tool(store, "search_sources", {"question": "gas output", "source_ids": ["eia"]})
        assert found["engine"] == "haystack-bm25"
        assert found["passages"] and "12 units" in found["passages"][0]["body"]
        assert found["ledger_written"] is False
        assert any(item["detail"].startswith("429") for item in found["source_errors"])

        timed = call_tool(store, "search_sources",
                          {"question": "gas output", "source_ids": ["federal-register"]})
        assert any("timeout" in item["detail"].lower() for item in timed["source_errors"])

        claim = call_tool(store, "get_claim", {"claim_id": "royalty", "source_id": "white-house"})
        assert claim["status"] == "stated"
        assert claim["quote"]
        assert "$200 billion" in claim["quote"]

        draft = call_tool(store, "propose_write",
                          {"headline": "SYNTHETIC draft", "body": "Pending human review."})
        assert draft["draft_id"] and draft["approved"] is False and draft["note_written"] is False
        assert store.note_count() == 0
        assert store.approve(draft["draft_id"])
        assert store.note_count() == 1
    finally:
        store.close()


def test_SYNTHETIC_schema_invalid_and_unknown_tool_are_visible():
    store = LiveStore()
    try:
        with pytest.raises(ToolError, match="question"):
            call_tool(store, "search_sources", {"source_ids": ["eia"]})
        with pytest.raises(ToolError, match="extra"):
            call_tool(store, "propose_write", {
                "headline": "x", "body": "y", "approve": True,
            })
        with pytest.raises(ToolError, match="Unknown claim_id"):
            call_tool(store, "get_claim", {"claim_id": "invented", "source_id": "ofac"})
        with pytest.raises(ToolError, match="Unknown tool"):
            call_tool(store, "apply_packet", {"headline": "no"})
    finally:
        store.close()


def test_SYNTHETIC_http_lists_and_invokes_mcp_tools(tmp_path):
    with TestClient(create_app(tmp_path / "SYNTHETIC-mcp.sqlite3")) as client:
        listed = client.get("/api/mcp/tools")
        assert listed.status_code == 200
        assert {item["name"] for item in listed.json()["tools"]} == {
            "search_sources", "get_claim", "propose_write",
        }
        assert listed.json()["pages"].startswith("Recorded")
        client.app.state.store.ingest("eia", live_document())
        search = client.post("/api/mcp/tools/search_sources",
                             json={"question": "gas output", "source_ids": ["eia"]})
        assert search.status_code == 200 and search.json()["passages"]
        claim = client.post("/api/mcp/tools/get_claim",
                            json={"claim_id": "gl_46d", "source_id": "ofac"})
        assert claim.status_code == 200 and claim.json()["status"] == "stated"
        draft = client.post("/api/mcp/tools/propose_write",
                            json={"headline": "SYNTHETIC", "body": "Do not persist yet."})
        assert draft.status_code == 200 and client.app.state.store.note_count() == 0
        invalid = client.post("/api/mcp/tools/search_sources", json={"source_ids": ["eia"]})
        assert invalid.status_code == 422
        unknown = client.post("/api/mcp/tools/apply_packet", json={})
        assert unknown.status_code == 404


def test_SYNTHETIC_official_mcp_client_invokes_each_tool():
    store = LiveStore()
    seed_live(store)
    bind_store(store)

    async def exercise():
        async with Client(desk_mcp, raise_exceptions=True) as client:
            tools = await client.list_tools()
            assert {item.name for item in tools.tools} == {
                "search_sources", "get_claim", "propose_write",
            }
            search = await client.call_tool("search_sources",
                                            {"question": "gas output", "source_ids": ["eia"]})
            assert not search.is_error
            payload = json.loads(search.content[0].text)
            assert payload["passages"] and payload["engine"] == "haystack-bm25"
            claim = await client.call_tool("get_claim",
                                           {"claim_id": "royalty", "source_id": "white-house"})
            assert not claim.is_error
            assert "$200 billion" in json.loads(claim.content[0].text)["quote"]
            draft = await client.call_tool("propose_write",
                                           {"headline": "SYNTHETIC", "body": "Pending."})
            assert not draft.is_error
            assert json.loads(draft.content[0].text)["note_written"] is False
            invalid = await client.call_tool("search_sources", {"source_ids": ["eia"]})
            assert invalid.is_error
            assert "question" in invalid.content[0].text

    try:
        asyncio.run(exercise())
        assert store.note_count() == 0
    finally:
        store.close()


def test_SYNTHETIC_stdio_mcp_server_invokes_tools(tmp_path):
    db = tmp_path / "SYNTHETIC-stdio.sqlite3"
    store = LiveStore(db)
    try:
        seed_live(store)
    finally:
        store.close()

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "infodesk.mcp_server"],
            env={**os.environ, "INFODESK_DB": str(db), "HAYSTACK_TELEMETRY_ENABLED": "False"},
            cwd=str(ROOT),
        )
        async with Client(params, raise_exceptions=True) as client:
            tools = await client.list_tools()
            assert {item.name for item in tools.tools} == {
                "search_sources", "get_claim", "propose_write",
            }
            search = await client.call_tool("search_sources",
                                            {"question": "gas output", "source_ids": ["eia"]})
            assert not search.is_error
            claim = await client.call_tool("get_claim",
                                           {"claim_id": "nabep", "source_id": "white-house"})
            assert not claim.is_error
            draft = await client.call_tool("propose_write",
                                           {"headline": "SYNTHETIC", "body": "stdio draft"})
            assert not draft.is_error
            assert json.loads(draft.content[0].text)["note_written"] is False

    asyncio.run(exercise())
    check = LiveStore(db)
    try:
        assert check.note_count() == 0
        drafts = check.snapshot()["drafts"]
        assert drafts and drafts[0]["status"] == "pending"
    finally:
        check.close()
