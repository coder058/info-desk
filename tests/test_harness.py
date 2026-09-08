from infodesk.harness import CASES, run_harness
from infodesk.tools import SourceTools, FetchError
from infodesk.store import Store


def test_unknown_license_is_none():
    tools = SourceTools(Store())
    assert tools.lookup_license("99Z") is None
    assert tools.lookup_license("46D")["code"] == "46D"


def test_429_then_success(monkeypatch):
    store = Store()
    tools = SourceTools(store, fail_first="retry-ok")
    try:
        tools.fetch_source("retry-ok")
        raise AssertionError("expected 429")
    except FetchError as exc:
        assert exc.status == 429
    record = tools.fetch_source("retry-ok")
    assert record.status == 200
    assert store.fetches() == [("retry-ok", 429), ("retry-ok", 200)]


def test_harness_checks_database_not_a_model_claim():
    report = run_harness()
    assert report["passed"] is True
    by_id = {row["id"]: row for row in report["cases"]}
    assert by_id["conflict-barrels"]["action"] == "open_incident"
    assert by_id["conflict-barrels"]["approved_writes"] == 0
    assert any(item["kind"] == "conflict" for item in by_id["conflict-barrels"]["findings"])
    assert by_id["single-source"]["action"] == "verify_first"
    assert by_id["jailbreak"]["approved_writes"] == 0
    assert any(item["kind"] == "policy_attack" for item in by_id["jailbreak"]["findings"])
    assert by_id["retry-429"]["db"]["drafts"].__len__() == 1
    statuses = [status for _, status in by_id["retry-429"]["db"]["fetches"]]
    assert statuses[:2] == [429, 200]
    assert by_id["human-reject"]["notes"] == 0
    assert by_id["human-reject"]["approved_writes"] == 0
    for row in report["cases"]:
        assert row["baseline_action"] == row["action"]
    assert len(CASES) == 5
