from __future__ import annotations

import re
from dataclasses import replace
from datetime import date

from .schema import Evidence, Quantity

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_DATE = re.compile(
    r"\b(\d{1,2}\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+20\d{2}|"
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+20\d{2})\b",
    re.I,
)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
# A sentence that lists what the page does *not* contain is not a claim.
_NEGATE = re.compile(
    r"\bdoes not name\b|"
    r"\bdoes not confirm\b|"
    r"\bnot an OFAC license\b|"
    r"\bnot the signed concession\b|"
    r"\bnot confirmation of\b",
    re.I,
)

# Named metrics so 65bn field reserves do not collide with 46bn U.S. reserves.
RULES = (
    ("oil_fields", re.compile(r"(\d+)\s+oil fields", re.I)),
    ("concession_years", re.compile(r"(\d+)-year (?:concessions|rights)", re.I)),
    (
        "field_reserves_billion_bbl",
        re.compile(
            r"17 oil fields with proven reserves of (?:approximately )?([\d.]+)\s+billion barrels",
            re.I,
        ),
    ),
    (
        "us_reserves_billion_bbl",
        re.compile(r"U\.S\. territorial proven reserves of roughly ([\d.]+)\s+billion", re.I),
    ),
    ("equity_percent", re.compile(r"(\d+)% (?:equity stake|ownership stake)", re.I)),
    (
        "offtake_percent",
        re.compile(r"(?:guaranteed )?(\d+)% of the (?:off-take|output)", re.I),
    ),
    ("capex_billion_usd", re.compile(r"\$(\d+) billion in new oil infrastructure", re.I)),
    ("royalty_billion_usd", re.compile(r"\$(\d+) billion in royalty", re.I)),
)

_LEAD = {
    "ofac": re.compile(r"does not name", re.I),
    "white-house": re.compile(r"North American Blue Energy Partners", re.I),
    "ap": re.compile(r"behind Chevron", re.I),
}


def strip_html(html: str) -> str:
    text = _TAG.sub(" ", html)
    return _WS.sub(" ", text).strip()


def split_sentences(text: str) -> list[str]:
    compact = _WS.sub(" ", text.replace("\n", " ")).strip()
    # Do not split on initials (J. Trump) or U.S. — only on a period after a lowercase letter or digit.
    parts = re.split(r"(?<=[a-z0-9)\"'])[.!?]\s+(?=[A-Z\"'])", compact)
    return [part.strip() for part in parts if part.strip()]


def is_negated(sentence: str) -> bool:
    return bool(_NEGATE.search(sentence))


def claimable_text(text: str) -> str:
    kept = [sent for sent in split_sentences(text) if not is_negated(sent)]
    return " ".join(kept)


def sentence_matching(text: str, pattern: str | re.Pattern[str]) -> str | None:
    compiled = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, re.I)
    for sent in split_sentences(text):
        if compiled.search(sent):
            return sent
    return None


def lead_quote(source_id: str, text: str) -> str:
    preferred = _LEAD.get(source_id)
    if preferred:
        hit = sentence_matching(text, preferred)
        if hit:
            return hit[:400]
    for sent in split_sentences(text):
        if len(sent) > 40:
            return sent[:400]
    return text[:280]


def parse_date_token(token: str) -> str | None:
    token = token.strip()
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", token)
    if match:
        return date(int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1))).isoformat()
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})", token)
    if match:
        return date(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2))).isoformat()
    return None


def extract_dates(text: str) -> list[str]:
    out: list[str] = []
    for match in _DATE.finditer(claimable_text(text)):
        parsed = parse_date_token(match.group(0))
        if parsed:
            out.append(parsed)
    return list(dict.fromkeys(out))


def extract_quantities(text: str, evidence: Evidence) -> list[Quantity]:
    found: list[Quantity] = []
    usable = claimable_text(text)
    for name, pattern in RULES:
        for match in pattern.finditer(usable):
            raw = match.group(0)
            value = float(match.group(1).replace(",", ""))
            sent = sentence_matching(text, re.escape(raw)) or evidence.quote
            found.append(
                Quantity(
                    name=name,
                    value=value,
                    unit=name,
                    raw=raw,
                    evidence=replace(evidence, quote=sent[:400]),
                )
            )
    return found


def ranking_phrases(text: str) -> list[str]:
    usable = claimable_text(text)
    found: list[str] = []
    if re.search(r"second[- ]largest private Venezuelan oil producer", usable, re.I):
        found.append("second-largest private Venezuelan oil producer")
    if re.search(r"second largest operator in Venezuela, behind Chevron", usable, re.I):
        found.append("second largest operator in Venezuela, behind Chevron")
    return found


def mentions_deal_terms(text: str) -> bool:
    usable = claimable_text(text)
    return bool(re.search(r"\bNABEP\b", usable) and re.search(r"17 oil fields", usable, re.I))


def sentences(text: str) -> list[str]:
    return [part for part in split_sentences(text) if len(part) > 40]
