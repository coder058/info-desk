from infodesk.desk import run_case
from infodesk.schema import Case
from infodesk.sources import INSTRUCTION
from infodesk.store import Store


def test_does_not_treat_ofac_as_the_deal():
    store = Store()
    case = Case(
        id="ofac-gap",
        title="t",
        instruction=INSTRUCTION,
        source_ids=("ofac", "white-house", "ap"),
        human="approve",
    )
    result, _ = run_case(case, store)
    assert result.proposal.action == "verify_first"
    joined = result.proposal.body.lower() + " ".join(item.summary.lower() for item in result.proposal.findings)
    assert "license" in joined
    assert result.approved_writes == 0
    assert "500,000" not in result.proposal.body
