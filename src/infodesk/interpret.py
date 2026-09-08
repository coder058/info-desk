from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import replace

from .schema import Finding, Proposal, Quantity
from .validate import conflict_findings, single_source_findings


def heuristic_propose(
    *,
    quantities: list[Quantity],
    policy: list[Finding],
    licenses_found: list[str],
    licenses_known: list[str],
    duplicate: bool,
) -> Proposal:
    findings: list[Finding] = list(policy)
    if duplicate:
        findings.append(
            Finding(kind="duplicate", summary="A draft with this body hash already exists.")
        )
    findings.extend(conflict_findings(quantities))
    if not any(item.kind == "conflict" for item in findings):
        findings.extend(single_source_findings(quantities))
    if policy:
        action = "open_incident"
        headline = "Do not publish: source tried to override desk policy."
        body = "A source asked the desk to ignore rules or write without approval. Policy unchanged. No database write."
    elif any(item.kind == "conflict" for item in findings):
        action = "open_incident"
        headline = "Conflicting figures. Do not pick a number."
        body = "Two sources report different barrels-per-day for the same field. Marked as a conflict. No figure is selected."
    elif any(item.kind == "single_source" for item in findings):
        action = "verify_first"
        headline = "One source only. Do not conclude."
        body = "A quantity sits on a single source. verify_first: no invented second source, no published conclusion."
    elif duplicate:
        action = "open_incident"
        headline = "Duplicate draft."
        body = "This note was already proposed. Not inserted again."
    else:
        action = "publish_draft"
        headline = "Draft alert ready for human approval."
        known = ", ".join(licenses_known) or "none looked up"
        body = (
            "Sources agree on the quoted terms. Licenses checked: "
            f"{known}. Mentioned in text: {', '.join(licenses_found) or 'none'}. "
            "Not published until a human approves."
        )
    return Proposal(
        action=action,
        headline=headline,
        body=body,
        findings=tuple(findings),
        interpreter="heuristic",
    )


def _ollama_generate(prompt: str) -> tuple[str, int]:
    payload = json.dumps(
        {
            "model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
            "prompt": prompt,
            "stream": False,
        }
    ).encode()
    req = urllib.request.Request(
        os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate"),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as response:
        data = json.loads(response.read().decode())
    text = str(data.get("response") or "")
    tokens = int(data.get("eval_count") or 0)
    return text, tokens


def ollama_propose(prompt: str, fallback: Proposal) -> tuple[Proposal, int]:
    try:
        raw, tokens = _ollama_generate(prompt)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return fallback, 0
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1]
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback, tokens
    action = str(payload.get("action") or fallback.action)
    return (
        replace(
            fallback,
            action=action if action in {"publish_draft", "open_incident", "verify_first"} else fallback.action,
            headline=str(payload.get("headline") or fallback.headline),
            body=str(payload.get("body") or fallback.body),
            interpreter="ollama",
        ),
        tokens,
    )
