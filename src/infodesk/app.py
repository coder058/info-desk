from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .desk import run_case
from .harness import CASES, DESK_CASE_ID, desk_snapshot, run_harness
from .schema import Case
from .sources import INSTRUCTION, SOURCES
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"

app = FastAPI(title="Info Desk", version="0.1.0")
store = Store()
_last_draft: dict[str, int] = {}


class HumanBody(BaseModel):
    decision: str


@app.get("/api/health")
def health():
    return {"ok": True, "writes": "approve() only", "desk": DESK_CASE_ID}


@app.get("/api/instruction")
def instruction():
    return {"text": INSTRUCTION}


@app.get("/api/cases")
def list_cases():
    return [
        {
            "id": case.id,
            "title": case.title,
            "source_ids": list(case.source_ids),
            "labels": [SOURCES[sid]["label"] for sid in case.source_ids],
        }
        for case in CASES
    ]


@app.get("/api/sources/{source_id}")
def source(source_id: str):
    spec = SOURCES.get(source_id)
    if spec is None:
        raise HTTPException(404)
    return spec


@app.get("/api/desk")
def desk():
    return desk_snapshot(store)


@app.post("/api/cases/{case_id}/run")
def run(case_id: str):
    case = next((item for item in CASES if item.id == case_id), None)
    if case is None:
        raise HTTPException(404)
    live = Case(**{**case.__dict__, "human": "none"})
    result, draft_id = run_case(live, store)
    _last_draft[case_id] = draft_id
    return {
        "action": result.proposal.action,
        "headline": result.proposal.headline,
        "body": result.proposal.body,
        "findings": result.artifacts["findings"],
        "quantities": result.artifacts["quantities"],
        "claims": result.artifacts.get("claims", []),
        "licenses": result.artifacts.get("licenses", []),
        "sources": result.artifacts.get("sources", []),
        "draft_id": draft_id,
        "db": result.artifacts["db"],
        "interpreter": result.interpreter,
        "latency_ms": result.latency_ms,
        "baseline_action": result.baseline_action,
    }


@app.post("/api/drafts/{draft_id}/decide")
def decide(draft_id: int, body: HumanBody):
    if body.decision == "approve":
        ok = store.approve(draft_id)
    elif body.decision == "reject":
        ok = store.reject(draft_id)
    else:
        raise HTTPException(400, "decision must be approve or reject")
    if not ok:
        raise HTTPException(409, "draft is not pending, or approve is not allowed for this action")
    return store.snapshot()


@app.get("/api/db")
def db():
    return store.snapshot()


@app.get("/api/harness")
def harness():
    return run_harness()


@app.get("/case.json")
def case_file():
    path = PUBLIC / "case.json"
    if not path.exists():
        raise HTTPException(404, "run python -m infodesk.harness first")
    return FileResponse(path)


@app.get("/harness.json")
def harness_file():
    path = PUBLIC / "harness.json"
    if not path.exists():
        raise HTTPException(404, "run python -m infodesk.harness first")
    return FileResponse(path)


if PUBLIC.exists():
    app.mount("/assets", StaticFiles(directory=PUBLIC), name="assets")


@app.get("/")
def index():
    page = PUBLIC / "index.html"
    if not page.exists():
        raise HTTPException(404, "public/index.html missing")
    return FileResponse(page)


def main() -> None:
    import uvicorn

    uvicorn.run("infodesk.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
