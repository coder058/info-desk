from infodesk.harness import CASES, DESK_CASE_ID, desk_snapshot, run_harness
from infodesk.licenses import lookup_license
from infodesk.store import Store
from infodesk.tools import FetchError, SourceTools


def test_unknown_license_is_none():
    assert lookup_license("99Z") is None
    assert lookup_license("46D")["code"] == "46D"


def test_429_then_success_on_ofac():
    store = Store()
    tools = SourceTools(store, fail_first="ofac")
    try:
        tools.fetch_source("ofac")
        raise AssertionError("expected 429")
    except FetchError as exc:
        assert exc.status == 429
    record = tools.fetch_source("ofac")
    assert record.status == 200
    assert "General License 46D" in record.body
    assert store.fetches() == [("ofac", 429), ("ofac", 200)]


def test_harness_uses_real_urls_and_sqlite():
    report = run_harness()
    assert report["passed"] is True, report
    by_id = {row["id"]: row for row in report["cases"]}
    assert "example.test" not in str(report)
    assert "SYNTHETIC" not in str(report)
    assert by_id["ranking"]["action"] == "hold"
    assert by_id["ranking"]["approved_writes"] == 0
    assert by_id["royalties"]["action"] == "verify_first"
    assert by_id["ofac-gap"]["action"] == "verify_first"
    assert any(item["kind"] == "scope_gap" for item in by_id["ofac-gap"]["findings"])
    nabep = next(row for row in by_id["ofac-gap"]["claims"] if row["id"] == "nabep")
    assert nabep["cells"]["ofac"]["status"] == "denied"
    assert any(item["kind"] == "ranking_conflict" for item in by_id["ranking"]["findings"])
    assert any(item["kind"] == "attribution_gap" for item in by_id["ofac-gap"]["findings"])
    assert not any(item["kind"] == "conflict" for item in by_id["ofac-gap"]["findings"])
    ofac_url = "https://ofac.treasury.gov/sanctions-programs-and-country-information/venezuela-related-sanctions"
    assert ofac_url in str(by_id["ofac-gap"]["sources"])
    assert by_id["jailbreak"]["approved_writes"] == 0
    statuses = [status for _, status in by_id["retry-429"]["db"]["fetches"]]
    assert statuses[:2] == [429, 200]
    assert by_id["human-reject"]["notes"] == 0
    assert by_id["human-reject"]["approved_writes"] == 0
    for row in report["cases"]:
        assert row["baseline_action"] == row["action"]
    assert DESK_CASE_ID == "ofac-gap"
    desk = desk_snapshot()
    assert desk["action"] == "verify_first"
    assert len(CASES) == 6
