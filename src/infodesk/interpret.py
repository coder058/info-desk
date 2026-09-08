from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import replace

from .claims import attribution_gaps
from .extract import mentions_deal_terms, ranking_phrases, sentence_matching
from .schema import Evidence, Finding, Proposal, Quantity
from .validate import conflict_findings, single_source_findings


def heuristic_propose(
    *,
    quantities: list[Quantity],
    policy: list[Finding],
    licenses_found: list[str],
    licenses_known: list[str],
    bodies: dict[str, str],
    evidence_by_source: dict[str, Evidence],
    duplicate: bool,
) -> Proposal:
    findings: list[Finding] = list(policy)
    if duplicate:
        findings.append(Finding(kind="duplicate", summary="A draft with this body hash already exists."))

    ranks: list[tuple[str, str]] = []
    for source_id, text in bodies.items():
        for phrase in ranking_phrases(text):
            ranks.append((source_id, phrase))
    if len({phrase for _, phrase in ranks}) > 1:
        rank_evidence = []
        seen: set[str] = set()
        for source_id, phrase in ranks:
            if source_id in seen or source_id not in evidence_by_source:
                continue
            seen.add(source_id)
            base = evidence_by_source[source_id]
            sent = sentence_matching(bodies[source_id], re.escape(phrase)) or base.quote
            rank_evidence.append(replace(base, quote=sent[:400]))
        findings.append(
            Finding(
                kind="ranking_conflict",
                summary=(
                    "White House calls NABEP the second-largest private Venezuelan oil producer. "
                    "AP calls it the second largest operator in Venezuela, behind Chevron. "
                    "Do not pick one ranking."
                ),
                evidence=tuple(rank_evidence),
            )
        )

    ofac_text = bodies.get("ofac", "")
    deal_sources = [sid for sid, text in bodies.items() if sid != "ofac" and mentions_deal_terms(text)]
    if ofac_text and deal_sources and not mentions_deal_terms(ofac_text):
        ofac_ev = evidence_by_source.get("ofac")
        extra = [evidence_by_source[sid] for sid in deal_sources if sid in evidence_by_source]
        findings.append(
            Finding(
                kind="scope_gap",
                summary=(
                    "OFAC lists general licenses for Venezuelan-origin oil and PDVSA. "
                    "It does not name NABEP, 17 fields, or 100-year concessions. "
                    "A license list is not confirmation of the fact-sheet deal."
                ),
                evidence=tuple(ev for ev in (ofac_ev, *extra) if ev is not None),
            )
        )

    for ap_quote, note, _claim_id in attribution_gaps(bodies):
        ap_ev = evidence_by_source.get("ap")
        wh_ev = evidence_by_source.get("white-house")
        findings.append(
            Finding(
                kind="attribution_gap",
                summary=(
                    "AP attributes prior Russian or Chinese operators to the White House. "
                    + note
                ),
                evidence=tuple(
                    ev
                    for ev in (
                        replace(ap_ev, quote=ap_quote[:400]) if ap_ev else None,
                        wh_ev,
                    )
                    if ev is not None
                ),
            )
        )

    findings.extend(conflict_findings(quantities))
    if not any(item.kind == "conflict" for item in findings):
        findings.extend(single_source_findings(quantities))

    licenses_note = ", ".join(licenses_known) or "none looked up"

    if policy:
        action = "hold"
        headline = "Do not publish: a source tried to override desk policy."
        body = (
            "Fetched text asked the desk to ignore rules or write without approval. "
            "Policy unchanged. No database write."
        )
    elif any(item.kind in {"ranking_conflict", "scope_gap", "conflict"} for item in findings):
        action = "verify_first" if any(item.kind == "scope_gap" for item in findings) else "hold"
        headline = "Hold the note. The documents do not say the same thing."
        body = (
            "White House and AP describe an announcement: 17 fields, 100-year rights, NABEP. "
            "The 65 billion barrels are field reserves in that announcement; "
            "the 46 billion barrels on the fact sheet are U.S. territorial reserves — different figures. "
            "AP attributes the 65 billion barrels' prior Russian/Chinese operators to the White House; "
            "that sentence is not in the stored fact sheet. "
            "OFAC, if in this batch, is a license list — not that contract. "
            f"Licenses on the OFAC recording include: {licenses_note}. "
            "Do not write that OFAC authorised the concessions. Do not pick a NABEP ranking."
        )
    elif set(bodies) == {"ofac"}:
        action = "verify_first"
        headline = "OFAC license list only."
        body = (
            "This recording is the Venezuela sanctions page. It authorises listed activities "
            "through general licenses "
            f"({licenses_note}). "
            "It is not confirmation of the White House oil fact sheet."
        )
    elif any(item.kind == "single_source" for item in findings):
        action = "verify_first"
        headline = "One source only on at least one figure."
        body = (
            "A figure in this batch (for example expected royalties of $200 billion) sits on one document. "
            "The 46 billion U.S. territorial barrels, if present, are not the 65 billion field barrels. "
            "verify_first: do not invent a second source."
        )
    else:
        action = "publish_draft"
        headline = "Draft: announcement terms that more than one source repeats."
        body = (
            "Where White House and AP both state 17 oil fields and 100-year rights, that is an "
            "announcement match, not proof the concessions are executed law. "
            f"OFAC licenses looked up: {licenses_note}. "
            "Not published until a human approves."
        )
    return Proposal(
        action=action,
        headline=headline,
        body=body,
        findings=tuple(findings),
        interpreter="heuristic",
    )


def _ollama_generate(prompt: str) -> tuple[str, int]:
    payload = json.dumps(
        {
            "model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
            "prompt": prompt,
            "stream": False,
        }
    ).encode()
    req = urllib.request.Request(
        os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate"),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as response:
        data = json.loads(response.read().decode())
    text = str(data.get("response") or "")
    tokens = int(data.get("eval_count") or 0)
    return text, tokens


def ollama_propose(prompt: str, fallback: Proposal) -> tuple[Proposal, int]:
    try:
        raw, tokens = _ollama_generate(prompt)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return fallback, 0
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1]
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback, tokens
    action = str(payload.get("action") or fallback.action)
    allowed = {"publish_draft", "hold", "verify_first"}
    return (
        replace(
            fallback,
            action=action if action in allowed else fallback.action,
            headline=str(payload.get("headline") or fallback.headline),
            body=str(payload.get("body") or fallback.body),
            interpreter="ollama",
        ),
        tokens,
    )
