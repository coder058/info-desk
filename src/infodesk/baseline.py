from __future__ import annotations

from .interpret import heuristic_propose
from .schema import Evidence, Finding, Quantity


def baseline_action(
    quantities: list[Quantity],
    policy: list[Finding],
    bodies: dict[str, str],
    evidence_by_source: dict[str, Evidence],
) -> str:
    return heuristic_propose(
        quantities=quantities,
        policy=policy,
        licenses_found=[],
        licenses_known=[],
        bodies=bodies,
        evidence_by_source=evidence_by_source,
        duplicate=False,
    ).action
