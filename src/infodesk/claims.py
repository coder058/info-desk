from __future__ import annotations

import re

from .extract import is_negated, sentence_matching

# One row per editorial claim. Status is taken from the sentence, not from a model.
CLAIMS: tuple[tuple[str, str, str], ...] = (
    (
        "nabep",
        "Names NABEP / North American Blue Energy Partners",
        r"\bNABEP\b|North American Blue Energy Partners",
    ),
    ("oil_fields", "17 oil fields", r"17 oil fields"),
    ("concession", "100-year concessions or rights", r"100-year (?:concessions|rights)"),
    (
        "field_reserves",
        "About 65 billion barrels in those fields",
        r"65 billion barrels",
    ),
    (
        "us_reserves",
        "U.S. territorial proven reserves of roughly 46 billion barrels",
        r"U\.S\. territorial proven reserves of roughly 46 billion",
    ),
    ("equity", "35% OSC / Pentagon stake", r"35%\s+(?:equity|ownership) stake"),
    ("offtake", "20% offtake or output at cost", r"20%\s+of the (?:off-take|output)"),
    ("capex", "$100 billion in new oil infrastructure", r"\$100 billion in new oil infrastructure"),
    (
        "royalty",
        "$200 billion expected royalties and tax payments",
        r"\$200 billion in royalty",
    ),
    (
        "rank_private",
        "Second-largest private Venezuelan oil producer",
        r"second-largest private Venezuelan oil producer",
    ),
    (
        "rank_chevron",
        "Second largest operator in Venezuela, behind Chevron",
        r"second largest operator in Venezuela, behind Chevron",
    ),
    (
        "prior_operators",
        "Prior operators described as Russian or Chinese",
        r"Russian or Chinese",
    ),
    (
        "gl_46d",
        "OFAC General License 46D — Venezuelan-origin oil or petrochemicals",
        r"General License 46D",
    ),
    (
        "gl_50c",
        "OFAC General License 50C — oil or gas sector operations",
        r"General License 50C",
    ),
    (
        "gl_52b",
        "OFAC General License 52B — Petróleos de Venezuela, S.A.",
        r"General License 52B",
    ),
    (
        "gl_49a",
        "OFAC General License 49A — contingent contracts for certain investment",
        r"General License 49A",
    ),
)

_ATTR = re.compile(r"the White House (said|disclosed)", re.I)


def classify_sentence(text: str, pattern: str) -> dict:
    """Four outcomes, kept apart on purpose.

    `not_named` means the capture carries a scope line stating the page does not
    mention the claim. That is still an absence, not the page denying the claim,
    so it must never be read as a rebuttal of the other sources.
    """
    hit = sentence_matching(text, pattern)
    if not hit:
        return {"status": "absent", "quote": ""}
    if is_negated(hit):
        return {"status": "not_named", "quote": hit}
    if _ATTR.search(hit):
        return {"status": "attributed", "quote": hit}
    return {"status": "stated", "quote": hit}


def build_matrix(bodies: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    for claim_id, label, pattern in CLAIMS:
        cells = {sid: classify_sentence(text, pattern) for sid, text in bodies.items()}
        rows.append({"id": claim_id, "label": label, "cells": cells})
    return rows


def attribution_gaps(bodies: dict[str, str]) -> list[tuple[str, str, str]]:
    """AP cites the White House for a fact the stored fact sheet does not contain."""
    ap = bodies.get("ap", "")
    wh = bodies.get("white-house", "")
    if not ap or not wh:
        return []
    gaps: list[tuple[str, str, str]] = []
    ap_sent = sentence_matching(ap, r"Russian or Chinese")
    if ap_sent and _ATTR.search(ap_sent) and not re.search(r"Russian or Chinese", wh, re.I):
        gaps.append(
            (
                ap_sent,
                "The stored White House fact sheet does not mention Russian or Chinese operators.",
                "prior_operators",
            )
        )
    return gaps
