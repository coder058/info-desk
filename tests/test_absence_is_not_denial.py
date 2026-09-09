"""An absent mention must never be scored as the source denying the claim."""

from infodesk.claims import build_matrix, classify_sentence
from infodesk.sources import SOURCES


def test_ofac_capture_is_absent_on_the_deal_claims_not_a_denial():
    bodies = {sid: spec["body"] for sid, spec in SOURCES.items()}
    rows = {row["id"]: row for row in build_matrix(bodies)}
    for claim_id in ("nabep", "oil_fields", "royalty"):
        cell = rows[claim_id]["cells"]["ofac"]
        assert cell["status"] == "absent", claim_id
        assert cell["quote"] == "", claim_id


def test_editorial_absence_notes_never_reach_the_evidence_text():
    # The recordings keep their original closing paragraphs for audit; sources.py
    # strips them, so no claim cell can quote an annotation as publisher prose.
    for spec in SOURCES.values():
        assert "This page lists general licenses." not in spec["body"]
        assert "This page is a White House fact sheet," not in spec["body"]


def test_a_real_negation_is_labelled_not_named_rather_than_denied():
    text = "The register does not name North American Blue Energy Partners anywhere."
    cell = classify_sentence(text, r"North American Blue Energy Partners")
    assert cell["status"] == "not_named"
    assert cell["status"] != "denied"
