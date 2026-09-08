from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .licenses import lookup_license
from .schema import Finding, Proposal, Quantity

KNOWN_ACTIONS = {"publish_draft", "hold", "verify_first"}


class InvalidProposal(ValueError):
    pass


def conflict_findings(quantities: list[Quantity]) -> list[Finding]:
    grouped: dict[str, list[Quantity]] = defaultdict(list)
    for item in quantities:
        grouped[item.name].append(item)
    findings: list[Finding] = []
    for name, group in grouped.items():
        values = {round(item.value, 6) for item in group}
        if len(values) < 2:
            continue
        findings.append(
            Finding(
                kind="conflict",
                summary=f"Sources disagree on {name}: {sorted(values)}.",
                evidence=tuple(item.evidence for item in group),
            )
        )
    return findings


def single_source_findings(quantities: list[Quantity]) -> list[Finding]:
    grouped: dict[str, list[Quantity]] = defaultdict(list)
    for item in quantities:
        grouped[item.name].append(item)
    findings: list[Finding] = []
    for name, group in grouped.items():
        sources = {item.evidence.source_id for item in group}
        values = {round(item.value, 6) for item in group}
        if len(sources) == 1 and len(values) == 1:
            findings.append(
                Finding(
                    kind="single_source",
                    summary=f"{name} appears in only one source.",
                    evidence=(group[0].evidence,),
                )
            )
    return findings


def validate_proposal(
    proposal: Proposal,
    *,
    quantities: list[Quantity],
    policy: list[Finding],
    mentioned_licenses: list[str],
) -> Proposal:
    if proposal.action not in KNOWN_ACTIONS:
        raise InvalidProposal("unknown action")
    if policy:
        return replace(proposal, action="hold")
    for code in mentioned_licenses:
        if lookup_license(code) is None:
            raise InvalidProposal(f"unknown license {code}")
    if "99Z" in proposal.body or "GL-99Z" in proposal.body:
        raise InvalidProposal("invented license")
    conflicts = conflict_findings(quantities)
    if conflicts and proposal.action == "publish_draft":
        raise InvalidProposal("cannot publish while quantities conflict")
    singles = single_source_findings(quantities)
    if singles and not conflicts and proposal.action == "publish_draft":
        if any(item.name == "royalty_billion_usd" for item in quantities):
            raise InvalidProposal("single-source royalty cannot publish")
    return proposal
