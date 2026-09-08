from __future__ import annotations

import re

from .schema import Evidence, Finding

_ATTACK = re.compile(
    r"ignore (?:all )?(?:the )?rules|ignore previous|publish (?:this )?(?:now|anyway)|"
    r"disable (?:the )?policy|write (?:the )?database without approval|"
    r"without approval",
    re.I,
)


def policy_hits(text: str, evidence: Evidence) -> list[Finding]:
    hits: list[Finding] = []
    for match in _ATTACK.finditer(text):
        quote = match.group(0)
        hits.append(
            Finding(
                kind="policy_attack",
                summary="Source text asked the desk to skip review or write without approval.",
                evidence=(
                    Evidence(
                        quote=quote,
                        url=evidence.url,
                        fetched_at=evidence.fetched_at,
                        label=evidence.label,
                        source_id=evidence.source_id,
                    ),
                ),
            )
        )
    return hits
