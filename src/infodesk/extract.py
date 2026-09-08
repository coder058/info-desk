from __future__ import annotations

import re
from datetime import date

from .schema import Evidence, Quantity

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_DATE = re.compile(
    r"\b(\d{1,2}\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+20\d{2}|\d{4}-\d{2}-\d{2})\b",
    re.I,
)
_LICENSE = re.compile(r"\b(?:General License\s+)?(\d{2}[A-Z])\b")
_URL = re.compile(r"https?://[^\s\"'<>]+")
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# 1.2 million barrels per day | 500,000 barrels per day | 500000 bpd
_BPD = re.compile(
    r"(?P<num>[\d,.]+)\s*(?P<million>million\s+)?(?:barrels?\s+per\s+day|bpd|b/d)",
    re.I,
)
_FIELDS = re.compile(r"\b(\d+)\s+oil fields\b", re.I)
_YEARS = re.compile(r"\b(\d+)-year\b", re.I)


def strip_html(html: str) -> str:
    text = _TAG.sub(" ", html)
    return _WS.sub(" ", text).strip()


def parse_date_token(token: str) -> str | None:
    token = token.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
        date.fromisoformat(token)
        return token
    match = re.fullmatch(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", token
    )
    if not match:
        return None
    day, month, year = int(match.group(1)), match.group(2).lower(), int(match.group(3))
    return date(year, _MONTHS[month], day).isoformat()


def _number(raw: str, million: bool) -> float:
    cleaned = raw.replace(",", "")
    value = float(cleaned)
    if million:
        value *= 1_000_000
    return value


def extract_quantities(text: str, evidence: Evidence) -> list[Quantity]:
    found: list[Quantity] = []
    for match in _BPD.finditer(text):
        value = _number(match.group("num"), bool(match.group("million")))
        found.append(
            Quantity(
                name="barrels_per_day",
                value=value,
                unit="bpd",
                raw=match.group(0),
                evidence=evidence,
            )
        )
    for match in _FIELDS.finditer(text):
        found.append(
            Quantity(
                name="oil_fields",
                value=float(match.group(1)),
                unit="fields",
                raw=match.group(0),
                evidence=evidence,
            )
        )
    for match in _YEARS.finditer(text):
        found.append(
            Quantity(
                name="concession_years",
                value=float(match.group(1)),
                unit="years",
                raw=match.group(0),
                evidence=evidence,
            )
        )
    return found


def extract_dates(text: str) -> list[str]:
    out: list[str] = []
    for match in _DATE.finditer(text):
        parsed = parse_date_token(match.group(0))
        if parsed:
            out.append(parsed)
    return out


def extract_licenses(text: str) -> list[str]:
    return list(dict.fromkeys(_LICENSE.findall(text)))


def extract_urls(text: str) -> list[str]:
    return _URL.findall(text)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]
