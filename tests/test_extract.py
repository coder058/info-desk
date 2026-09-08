from infodesk.extract import extract_quantities, ranking_phrases
from infodesk.licenses import lookup_license, parse_ofac_licenses
from infodesk.schema import Evidence
from infodesk.sources import SOURCES


def _ev(source_id="white-house"):
    spec = SOURCES[source_id]
    return Evidence(
        quote="q",
        url=spec["url"],
        fetched_at=spec["fetched_at"],
        label="PUBLIC_RECORDING",
        source_id=source_id,
    )


def test_real_white_house_figures():
    text = SOURCES["white-house"]["body"]
    found = {item.name: item.value for item in extract_quantities(text, _ev())}
    assert found["oil_fields"] == 17
    assert found["concession_years"] == 100
    assert found["field_reserves_billion_bbl"] == 65
    assert found["us_reserves_billion_bbl"] == 46
    assert found["royalty_billion_usd"] == 200
    royalty = next(item for item in extract_quantities(text, _ev()) if item.name == "royalty_billion_usd")
    assert "200 billion" in royalty.evidence.quote
    assert "17 oil fields" not in royalty.evidence.quote
    assert found["capex_billion_usd"] == 100
    assert "second-largest private Venezuelan oil producer" in ranking_phrases(text)


def test_ap_quotes_chevron_and_does_not_invent_royalties():
    text = SOURCES["ap"]["body"]
    names = {item.name for item in extract_quantities(text, _ev("ap"))}
    assert "royalty_billion_usd" not in names
    assert "oil_fields" in names
    assert "behind Chevron" in ranking_phrases(text)[0]


def test_ofac_licenses_come_from_the_page():
    licenses = parse_ofac_licenses()
    assert licenses["46D"]["issued"] == "August 27, 2026"
    assert "oil" in licenses["46D"]["title"].lower() or "Oil" in licenses["46D"]["title"]
    assert lookup_license("52B")["code"] == "52B"
    assert lookup_license("99Z") is None
    assert "NABEP" not in SOURCES["ofac"]["body"]


def test_ofac_negation_is_not_extracted_as_a_claim():
    found = {item.name for item in extract_quantities(SOURCES["ofac"]["body"], _ev("ofac"))}
    assert "oil_fields" not in found
    assert "concession_years" not in found
    assert "field_reserves_billion_bbl" not in found


def test_field_reserves_are_not_us_territorial_reserves():
    text = SOURCES["white-house"]["body"]
    found = {item.name: item.value for item in extract_quantities(text, _ev())}
    assert found["field_reserves_billion_bbl"] != found["us_reserves_billion_bbl"]
    assert found["field_reserves_billion_bbl"] == 65
    assert found["us_reserves_billion_bbl"] == 46
