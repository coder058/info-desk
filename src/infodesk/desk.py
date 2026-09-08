from __future__ import annotations

import time

from .baseline import baseline_action
from .claims import build_matrix
from .extract import extract_dates, extract_quantities, lead_quote, strip_html
from .interpret import heuristic_propose, ollama_propose
from .licenses import parse_ofac_licenses
from .policy import policy_hits
from .schema import Case, Evidence, Proposal, RunResult
from .sources import SOURCES
from .store import Store
from .tools import FetchError, SourceTools
from .validate import InvalidProposal, validate_proposal


def _fetch_with_retry(tools: SourceTools, source_id: str, retries: int = 1):
    last: FetchError | None = None
    for _ in range(retries + 1):
        try:
            return tools.fetch_source(source_id)
        except FetchError as exc:
            last = exc
            if exc.status != 429:
                raise
    assert last is not None
    raise last


def run_case(case: Case, store: Store, *, use_ollama: bool = False) -> tuple[RunResult, int]:
    started = time.perf_counter()
    tools = SourceTools(
        store,
        fail_first=case.fail_first,
        inject_attack_on="ofac" if case.inject_attack else None,
    )
    quantities = []
    policy = []
    licenses_found: list[str] = []
    licenses_known: list[str] = []
    dates: list[str] = []
    bodies: dict[str, str] = {}
    evidence_by_source: dict[str, Evidence] = {}

    for source_id in case.source_ids:
        record = _fetch_with_retry(tools, source_id)
        text = strip_html(record.body)
        bodies[source_id] = text
        snippet = lead_quote(source_id, text)
        evidence = Evidence(
            quote=snippet[:400],
            url=record.url,
            fetched_at=record.fetched_at,
            label=record.label,
            source_id=source_id,
        )
        evidence_by_source[source_id] = evidence
        quantities.extend(extract_quantities(text, evidence))
        policy.extend(policy_hits(text, evidence))
        if source_id == "ofac":
            parsed = parse_ofac_licenses(text)
            for code in parsed:
                if code not in licenses_found:
                    licenses_found.append(code)
                looked = tools.lookup_license(code)
                if looked and code not in licenses_known:
                    licenses_known.append(code)

    tools.search_prior_notes(case.id)
    heuristic = heuristic_propose(
        quantities=quantities,
        policy=policy,
        licenses_found=licenses_found,
        licenses_known=licenses_known,
        bodies=bodies,
        evidence_by_source=evidence_by_source,
        duplicate=False,
    )
    tokens = 0
    proposal: Proposal = heuristic
    if use_ollama:
        proposal, tokens = ollama_propose(
            "Return JSON with action, headline, body. Do not invent OFAC licenses.",
            heuristic,
        )
    try:
        proposal = validate_proposal(
            proposal,
            quantities=quantities,
            policy=policy,
            mentioned_licenses=licenses_found,
        )
    except InvalidProposal:
        proposal = heuristic

    draft_id = store.insert_draft(
        case.id, proposal.action, proposal.headline, proposal.body, proposal.interpreter
    )
    if case.human == "approve":
        store.approve(draft_id)
    elif case.human == "reject":
        store.reject(draft_id)

    result = RunResult(
        case_id=case.id,
        proposal=proposal,
        notes=store.note_count(),
        approved_writes=store.approved_write_count(),
        fetches=store.fetches(),
        latency_ms=(time.perf_counter() - started) * 1000,
        interpreter=proposal.interpreter,
        ollama_tokens=tokens,
        baseline_action=baseline_action(quantities, policy, bodies, evidence_by_source),
        artifacts={
            "draft_id": draft_id,
            "dates": dates + extract_dates(" ".join(bodies.values())),
            "licenses_found": licenses_found,
            "licenses_known": licenses_known,
            "licenses": [tools.lookup_license(code) for code in licenses_known if tools.lookup_license(code)],
            "claims": build_matrix(bodies),
            "quantities": [
                {
                    "name": item.name,
                    "value": item.value,
                    "raw": item.raw,
                    "source": item.evidence.source_id,
                    "url": item.evidence.url,
                    "quote": item.evidence.quote,
                }
                for item in quantities
            ],
            "findings": [
                {
                    "kind": item.kind,
                    "summary": item.summary,
                    "quotes": [ev.quote for ev in item.evidence],
                    "urls": [ev.url for ev in item.evidence],
                }
                for item in proposal.findings
            ],
            "sources": [
                {
                    "id": sid,
                    "url": evidence_by_source[sid].url,
                    "quote": evidence_by_source[sid].quote,
                    "title": SOURCES[sid]["title"],
                    "kind": SOURCES[sid]["kind"],
                    "fetched_at": SOURCES[sid]["fetched_at"],
                }
                for sid in case.source_ids
                if sid in evidence_by_source
            ],
            "db": store.snapshot(),
        },
    )
    return result, draft_id
