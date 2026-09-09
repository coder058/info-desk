from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "recordings"

INSTRUCTION = (
    "This batch of sources has arrived. Compare them, mark what is not "
    "verifiable, and prepare a draft alert. Do not publish without approval."
)


def _txt(name: str) -> str:
    return (REC / name).read_text(encoding="utf-8")


def _ap() -> dict:
    return json.loads((REC / "ap-oil.json").read_text(encoding="utf-8"))


def load_sources() -> dict:
    ap = _ap()
    # SOURCE: these final paragraphs were editorial additions in the original
    # recordings, not quotations from the publishers. Keep the files unchanged
    # for audit, but exclude annotations and capture headers from evidence.
    ofac_raw = _txt("ofac-venezuela.txt")
    wh_raw = _txt("white-house-oil.txt")
    ofac = ofac_raw.split("\n\n", 1)[1].split("\nThis page lists general licenses.")[0].strip()
    wh = wh_raw.split("\n\n", 1)[1].split("\nThis page is a White House fact sheet,")[0].strip()
    return {
        "ofac": {
            "url": "https://ofac.treasury.gov/sanctions-programs-and-country-information/venezuela-related-sanctions",
            "label": "PUBLIC_RECORDING",
            "title": "OFAC — Venezuela-related sanctions",
            "kind": "ofac_licenses",
            "fetched_at": "2026-09-08T13:15:00Z",
            "body": ofac,
            "capture_note": "Selected license-list excerpts; not the full OFAC page. Original editorial annotation excluded from evidence.",
        },
        "white-house": {
            "url": "https://www.whitehouse.gov/fact-sheets/2026/08/fact-sheet-president-donald-j-trump-announces-historic-oil-agreement-to-secure-american-energy-dominance-and-drive-venezuelas-economic-recovery/",
            "label": "PUBLIC_RECORDING",
            "title": "White House fact sheet — 31 August 2026",
            "kind": "white_house_fact_sheet",
            "fetched_at": "2026-09-08T13:15:00Z",
            "body": wh,
            "capture_note": "Stored fact-sheet excerpts, not signed contracts. Original editorial annotation excluded from evidence.",
        },
        "ap": {
            "url": ap["url"],
            "label": "PUBLIC_RECORDING",
            "title": ap["title"],
            "kind": "ap_report",
            "fetched_at": ap["fetched_at"],
            "body": ap["body"],
            "capture_note": "Selected AP excerpts supplied with this project, not the full article. Absence here does not establish absence in the article.",
        },
    }


SOURCES = load_sources()
