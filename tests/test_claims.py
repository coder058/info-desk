from infodesk.claims import build_matrix
from infodesk.sources import SOURCES


def test_matrix_is_the_documents_not_a_guess():
    bodies = {sid: spec["body"] for sid, spec in SOURCES.items()}
    rows = {row["id"]: row for row in build_matrix(bodies)}
    assert rows["nabep"]["cells"]["ofac"]["status"] == "denied"
    assert rows["nabep"]["cells"]["white-house"]["status"] == "stated"
    assert rows["nabep"]["cells"]["ap"]["status"] == "stated"
    assert rows["oil_fields"]["cells"]["ofac"]["status"] == "denied"
    assert rows["royalty"]["cells"]["white-house"]["status"] == "stated"
    assert rows["royalty"]["cells"]["ap"]["status"] == "absent"
    assert rows["royalty"]["cells"]["ofac"]["status"] == "absent"
    assert rows["rank_private"]["cells"]["white-house"]["status"] == "stated"
    assert rows["rank_chevron"]["cells"]["ap"]["status"] == "stated"
    assert rows["rank_chevron"]["cells"]["white-house"]["status"] == "absent"
    assert rows["prior_operators"]["cells"]["ap"]["status"] == "attributed"
    assert rows["prior_operators"]["cells"]["white-house"]["status"] == "absent"
    assert rows["gl_46d"]["cells"]["ofac"]["status"] == "stated"
    assert rows["gl_46d"]["cells"]["white-house"]["status"] == "absent"
    assert rows["us_reserves"]["cells"]["white-house"]["status"] == "stated"
    assert rows["us_reserves"]["cells"]["ap"]["status"] == "absent"


def test_equity_on_ap_is_attributed_to_the_white_house():
    bodies = {sid: spec["body"] for sid, spec in SOURCES.items()}
    rows = {row["id"]: row for row in build_matrix(bodies)}
    assert rows["equity"]["cells"]["ap"]["status"] == "attributed"
    assert "White House disclosed" in rows["equity"]["cells"]["ap"]["quote"]
