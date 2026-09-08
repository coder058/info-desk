from __future__ import annotations

from .interpret import heuristic_propose
from .schema import Finding, Quantity


def baseline_action(
    quantities: list[Quantity],
    policy: list[Finding],
    duplicate: bool,
) -> str:
    """Regex/heuristic path with no model. Same rules as the desk validator."""
    return heuristic_propose(
        quantities=quantities,
        policy=policy,
        licenses_found=[],
        licenses_known=[],
        duplicate=duplicate,
    ).action
