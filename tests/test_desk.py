from infodesk.desk import run_case
from infodesk.schema import Case
from infodesk.store import Store
from infodesk.fixtures import INSTRUCTION


def test_conflict_does_not_select_a_figure():
    store = Store()
    case = Case(
        id="conflict-barrels",
        title="t",
        instruction=INSTRUCTION,
        source_ids=("barrels-a", "barrels-b"),
        human="approve",
        expect_action="open_incident",
    )
    result, _ = run_case(case, store)
    assert result.proposal.action == "open_incident"
    assert "500000" not in result.proposal.body.replace(",", "")
    assert result.approved_writes == 0
