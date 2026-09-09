"""The same evidence payload drives the local API and the static replay."""
from datetime import datetime, timezone
from itertools import combinations

from .desk import run_case
from .schema import Case
from .sources import INSTRUCTION, SOURCES
from .store import Store


def analyse(source_ids, store: Store, *, use_ollama=False, case: Case | None = None) -> dict:
    ordered = tuple(sid for sid in SOURCES if sid in source_ids)
    if not ordered or len(ordered) != len(source_ids):
        raise ValueError("Choose unique, registered source IDs")
    key = "+".join(ordered)
    case = case or Case(id=key, title="Selected source comparison", instruction=INSTRUCTION, source_ids=ordered)
    result, draft_id = run_case(case, store, use_ollama=use_ollama)
    return {
        "id": case.id, "selection_key": key, "source_ids": list(ordered),
        "title": case.title, "action": result.proposal.action,
        "headline": result.proposal.headline, "body": result.proposal.body,
        "interpreter": result.interpreter, "latency_ms": result.latency_ms,
        "ollama_tokens": result.ollama_tokens,
        "baseline_action": result.baseline_action, "draft_id": draft_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **result.artifacts,
    }


def build_bundle() -> dict:
    selections = {}
    # SOURCE: enumerate every non-empty subset of the registered recordings.
    for size in range(1, len(SOURCES) + 1):
        for subset in combinations(SOURCES, size):
            store = Store()
            try:
                payload = analyse(subset, store)
                selections[payload["selection_key"]] = payload
            finally:
                store.close()
    return {
        "mode": "recorded_replay", "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [{"id": sid, **{k: v for k, v in spec.items() if k != "body"}}
                    for sid, spec in SOURCES.items()],
        "selections": selections,
    }
