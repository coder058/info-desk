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
    ofac = _txt("ofac-venezuela.txt")
    wh = _txt("white-house-oil.txt")
    return {
        "ofac": {
            "url": "https://ofac.treasury.gov/sanctions-programs-and-country-information/venezuela-related-sanctions",
            "label": "PUBLIC_RECORDING",
            "title": "OFAC — Venezuela-related sanctions",
            "kind": "ofac_licenses",
            "fetched_at": "2026-09-08T13:15:00Z",
            "body": ofac,
        },
        "white-house": {
            "url": "https://www.whitehouse.gov/fact-sheets/2026/08/fact-sheet-president-donald-j-trump-announces-historic-oil-agreement-to-secure-american-energy-dominance-and-drive-venezuelas-economic-recovery/",
            "label": "PUBLIC_RECORDING",
            "title": "White House fact sheet — 31 August 2026",
            "kind": "white_house_fact_sheet",
            "fetched_at": "2026-09-08T13:15:00Z",
            "body": wh,
        },
        "ap": {
            "url": ap["url"],
            "label": "PUBLIC_RECORDING",
            "title": ap["title"],
            "kind": "ap_report",
            "fetched_at": ap["fetched_at"],
            "body": ap["body"],
        },
    }


SOURCES = load_sources()
