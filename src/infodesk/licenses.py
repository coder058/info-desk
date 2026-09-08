from __future__ import annotations

import re

from .sources import SOURCES

_GL = re.compile(
    r"Venezuela General License ([0-9]+[A-Z]?)\s*[-–]\s*(.+?)\s*\(([A-Za-z]+ \d+, \d{4})\)"
)


def parse_ofac_licenses(text: str | None = None) -> dict[str, dict]:
    body = text if text is not None else SOURCES["ofac"]["body"]
    found: dict[str, dict] = {}
    for match in _GL.finditer(body):
        code, title, issued = match.group(1), match.group(2).strip(), match.group(3)
        found[code] = {
            "code": code,
            "title": title,
            "issued": issued,
            "url": SOURCES["ofac"]["url"],
            "label": "PUBLIC_RECORDING",
        }
    return found


def lookup_license(code: str) -> dict | None:
    return parse_ofac_licenses().get(code)
