from infodesk.extract import extract_licenses, extract_quantities, parse_date_token, strip_html
from infodesk.schema import Evidence


def _ev():
    return Evidence(
        quote="q",
        url="https://example.test/a",
        fetched_at="2026-09-08T12:00:00Z",
        label="SYNTHETIC",
        source_id="barrels-a",
    )


def test_bpd_and_million():
    text = "500,000 barrels per day and 1.2 million barrels per day"
    found = extract_quantities(text, _ev())
    values = sorted(item.value for item in found)
    assert values == [500000.0, 1200000.0]


def test_dates_and_licenses():
    text = strip_html("<p>General License 46D on 21 August 2026.</p>")
    assert parse_date_token("21 August 2026") == "2026-08-21"
    assert "46D" in extract_licenses(text)
