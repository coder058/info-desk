"""Local MCP tools over the existing desk. Haystack ranks; approve() still writes notes."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .claims import CLAIMS, classify_sentence
from .connectors import FEEDS
from .sources import SOURCES

LIVE_SOURCE_IDS = tuple(FEEDS)

_bound_store = None


class ToolError(ValueError):
    """Visible tool-schema or tool-dispatch failure. Not a silent fallback."""


def bind_store(store) -> None:
    global _bound_store
    _bound_store = store


def current_store():
    if _bound_store is None:
        raise ToolError("MCP store is not bound. Start the local app or stdio server.")
    return _bound_store


class SearchSourcesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    source_ids: list[Literal["eia", "federal-register", "ofac-live"]] = Field(
        min_length=1, max_length=len(LIVE_SOURCE_IDS)
    )
    document_ids: list[str] = Field(default_factory=list, max_length=10)


class GetClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(min_length=1, max_length=40)
    source_id: Literal["ofac", "white-house", "ap"]


class ProposeWriteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    case_id: str = Field(default="mcp", min_length=1, max_length=80)


def search_sources(store, payload: SearchSourcesInput) -> dict:
    """Retrieve latest captured passages via the live Haystack BM25 path."""
    if len(set(payload.source_ids)) != len(payload.source_ids):
        raise ToolError("Choose each live source at most once")
    checks = store.latest_checks()
    source_errors = []
    for source_id in payload.source_ids:
        check = checks.get(source_id)
        if not check:
            continue
        detail = check.get("detail") or ""
        if check.get("status") in {"error", "cooldown"} or "429" in detail or "timeout" in detail.lower():
            source_errors.append({
                "source_id": source_id,
                "status": check.get("status"),
                "detail": detail,
            })
    passages = store.retrieve(payload.question, payload.source_ids, payload.document_ids)
    return {
        "passages": passages,
        "source_errors": source_errors,
        "engine": "haystack-bm25",
        "ledger_written": False,
        "approved": False,
    }


def get_claim(store, payload: GetClaimInput) -> dict:
    """Return one recorded claim cell and its exact supporting sentence."""
    spec = next((item for item in CLAIMS if item[0] == payload.claim_id), None)
    if spec is None:
        raise ToolError(f"Unknown claim_id: {payload.claim_id}")
    source = SOURCES[payload.source_id]
    cell = classify_sentence(source["body"], spec[2])
    return {
        "claim_id": payload.claim_id,
        "label": spec[1],
        "source_id": payload.source_id,
        "status": cell["status"],
        "quote": cell["quote"],
        "url": source["url"],
        "ledger_written": False,
        "approved": False,
    }


def propose_write(store, payload: ProposeWriteInput) -> dict:
    """Insert a pending draft only. This tool never calls approve()."""
    draft_id = store.insert_draft(
        payload.case_id, "publish_draft", payload.headline, payload.body, "mcp_propose_write"
    )
    return {
        "draft_id": draft_id,
        "status": "pending",
        "note_written": False,
        "approved": False,
        "notes": store.note_count(),
        "requires": "Human store.approve(draft_id) or POST /api/drafts/{id}/decide. This tool cannot approve.",
    }


TOOLS = {
    "search_sources": {
        "description": "Retrieve evidence passages from latest live captures using Haystack BM25. Does not fetch, ingest, or approve.",
        "input": SearchSourcesInput,
        "run": search_sources,
        "read_only": True,
    },
    "get_claim": {
        "description": "Return one recorded claim cell and the exact supporting sentence from the stored excerpt.",
        "input": GetClaimInput,
        "run": get_claim,
        "read_only": True,
    },
    "propose_write": {
        "description": "Create a pending draft note. A separate human approve() is required before a note is written.",
        "input": ProposeWriteInput,
        "run": propose_write,
        "read_only": False,
    },
}


def list_tools() -> list[dict]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["input"].model_json_schema(),
            "readOnly": spec["read_only"],
        }
        for name, spec in TOOLS.items()
    ]


def call_tool(store, name: str, arguments: dict | None) -> dict:
    spec = TOOLS.get(name)
    if spec is None:
        raise ToolError(f"Unknown tool: {name}")
    try:
        payload = spec["input"].model_validate(arguments or {})
    except ValidationError as exc:
        raise ToolError(str(exc)) from exc
    return spec["run"](store, payload)
