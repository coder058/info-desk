"""stdio MCP server for the local Info Desk tools.

Haystack retrieves; this process does not approve drafts. Run:
`python -m infodesk.mcp_server` after `pip install -e .`.
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .live_store import LiveStore
from .mcp_tools import bind_store, call_tool, current_store

ROOT = Path(__file__).resolve().parents[2]

desk_mcp = MCPServer("Info Desk")


@desk_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def search_sources(
    question: str,
    source_ids: list[str],
    document_ids: list[str] | None = None,
) -> dict:
    """Retrieve live captured passages with the Haystack BM25 pipeline.

    Read-only. Does not fetch sources, write the ledger, or approve drafts.
    Empty results stay empty. 429/timeout source checks stay visible.
    """
    return call_tool(current_store(), "search_sources", {
        "question": question,
        "source_ids": source_ids,
        "document_ids": document_ids or [],
    })


@desk_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def get_claim(claim_id: str, source_id: str) -> dict:
    """Return one recorded claim cell and its exact supporting sentence."""
    return call_tool(current_store(), "get_claim", {"claim_id": claim_id, "source_id": source_id})


@desk_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def propose_write(headline: str, body: str, case_id: str = "mcp") -> dict:
    """Create a pending draft only. This tool cannot approve or write a note."""
    return call_tool(current_store(), "propose_write", {
        "headline": headline, "body": body, "case_id": case_id,
    })


def main() -> None:
    store = LiveStore(os.environ.get("INFODESK_DB", str(ROOT / "data" / "desk.sqlite3")))
    bind_store(store)
    try:
        desk_mcp.run("stdio")
    finally:
        store.close()


if __name__ == "__main__":
    main()
