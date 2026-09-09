from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .harness import CASES, DESK_CASE_ID, desk_snapshot, run_harness
from .sources import SOURCES
from .store import Store
from .workbench import analyse
from .live_store import LiveStore
from .live_service import LiveRequest, LiveService

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"


class HumanBody(BaseModel):
    decision: Literal["approve", "reject"]


class AnalysisBody(BaseModel):
    # SOURCE: input bounded by the three allowlisted recordings, no arbitrary URLs.
    source_ids: list[Literal["ofac", "white-house", "ap"]] = Field(min_length=1, max_length=len(SOURCES))
    use_model: bool = False


def create_app(db_path: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = LiveStore(db_path or os.environ.get("INFODESK_DB", str(ROOT / "data" / "desk.sqlite3")))
        app.state.live = LiveService(app.state.store)
        try:
            yield
        finally:
            app.state.live.close()
            app.state.store.close()

    app = FastAPI(title="Info Desk", version="0.3.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])
    run_lock = RLock()

    @app.middleware("http")
    async def protect_local_writes(request: Request, call_next):
        # Local single-user API, not an unauthenticated public publishing service.
        origin = request.headers.get("origin")
        if request.method == "POST" and origin:
            if urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def store() -> Store:
        return app.state.store

    def execute(source_ids, *, use_model=False, case=None):
        if use_model and not os.environ.get("OLLAMA_URL"):
            raise HTTPException(503, "Optional model not configured. Deterministic analysis is available.")
        with run_lock:
            try:
                payload = analyse(source_ids, store(), use_ollama=use_model, case=case)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            payload["run_id"] = store().save_run(payload["id"], payload)
            return payload

    @app.get("/api/health")
    def health():
        return {"ok": True, "mode": "local_api", "model_available": bool(os.environ.get("OLLAMA_URL")),
                "storage": "sqlite", "desk": DESK_CASE_ID}

    @app.get("/api/cases")
    def cases():
        return [{"id": case.id, "title": case.title, "source_ids": list(case.source_ids)} for case in CASES]

    @app.get("/api/live/status")
    def live_status():
        return app.state.live.snapshot()

    @app.post("/api/live/{kind}", status_code=202)
    def live_submit(kind: Literal["sync", "ask"], body: LiveRequest):
        try:
            return app.state.live.submit(kind, body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/live/jobs/{job_id}")
    def live_job(job_id: str):
        result = store().job(job_id)
        if result is None:
            raise HTTPException(404, "Unknown live job")
        return result

    @app.post("/api/live/jobs/{job_id}/cancel")
    def live_cancel(job_id: str):
        if not store().cancel_job(job_id):
            raise HTTPException(409, "Job is already finished or missing")
        return store().job(job_id)

    @app.get("/api/live/documents/{document_id}")
    def live_document(document_id: str):
        import difflib
        document = store().document(document_id)
        if document is None:
            raise HTTPException(404, "Unknown document")
        versions = document["versions"]
        document["diff"] = "\n".join(difflib.unified_diff(
            versions[1]["body"].splitlines(), versions[0]["body"].splitlines(),
            fromfile=versions[1]["received_at"], tofile=versions[0]["received_at"], lineterm=""
        )) if len(versions) > 1 else None
        return document

    @app.get("/api/sources/{source_id}")
    def source(source_id: str):
        if source_id not in SOURCES:
            raise HTTPException(404, "Unknown source")
        return SOURCES[source_id]

    @app.get("/api/desk")
    def desk():
        # Read-only preview. GET must not insert local drafts or fetch events.
        return desk_snapshot()

    @app.post("/api/analyses")
    def run(body: AnalysisBody):
        return execute(body.source_ids, use_model=body.use_model)

    @app.post("/api/cases/{case_id}/run")
    def run_scenario(case_id: str):
        case = next((item for item in CASES if item.id == case_id), None)
        if case is None:
            raise HTTPException(404, "Unknown case")
        return execute(case.source_ids, case=replace(case, human="none"))

    @app.post("/api/drafts/{draft_id}/decide")
    def decide(draft_id: int, body: HumanBody):
        with run_lock:
            ok = store().approve(draft_id) if body.decision == "approve" else store().reject(draft_id)
            if not ok:
                raise HTTPException(409, "Draft already decided, missing, or approval blocked by policy")
            return store().snapshot()

    @app.get("/api/db")
    def db():
        return store().snapshot()

    @app.get("/api/runs")
    def runs():
        return store().list_runs()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        result = store().get_run(run_id)
        if result is None:
            raise HTTPException(404, "Unknown run")
        return result

    @app.get("/api/harness")
    def harness():
        # Each evaluation uses an isolated in-memory database, never the user's ledger.
        return run_harness()

    @app.get("/")
    def index():
        return FileResponse(PUBLIC / "index.html")

    @app.get("/{filename}")
    def asset(filename: str):
        if filename not in {"desk.css", "desk.js", "live.css", "live.js", "case.json", "harness.json", "workbench.json"}:
            raise HTTPException(404)
        path = PUBLIC / filename
        if not path.is_file():
            raise HTTPException(404, "Generate replay files with python -m infodesk.harness")
        return FileResponse(path)

    return app


app = create_app()


def main() -> None:
    import uvicorn
    uvicorn.run("infodesk.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
