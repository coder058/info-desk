from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Label = Literal["PUBLIC_RECORDING"]
Action = Literal["publish_draft", "hold", "verify_first"]
FindingKind = Literal[
    "conflict",
    "single_source",
    "policy_attack",
    "duplicate",
    "scope_gap",
    "ranking_conflict",
    "attribution_gap",
    "unverified",
]


@dataclass(frozen=True)
class Evidence:
    quote: str
    url: str
    fetched_at: str
    label: Label
    source_id: str


@dataclass(frozen=True)
class Quantity:
    name: str
    value: float
    unit: str
    raw: str
    evidence: Evidence


@dataclass(frozen=True)
class Finding:
    kind: FindingKind
    summary: str
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class Proposal:
    action: Action
    headline: str
    body: str
    findings: tuple[Finding, ...]
    interpreter: str


@dataclass(frozen=True)
class FetchRecord:
    source_id: str
    status: int
    fetched_at: str
    body: str
    url: str
    label: Label


@dataclass
class Case:
    id: str
    title: str
    instruction: str
    source_ids: tuple[str, ...]
    human: Literal["approve", "reject", "none"] = "none"
    expect_action: Action = "verify_first"
    expect_notes: int = 0
    expect_approved_writes: int = 0
    expect_finding_kinds: tuple[FindingKind, ...] = ()
    expect_min_fetches: int = 0
    expect_status_sequence: tuple[int, ...] = ()
    inject_attack: bool = False
    fail_first: str | None = None


@dataclass
class RunResult:
    case_id: str
    proposal: Proposal
    notes: int
    approved_writes: int
    fetches: list[tuple[str, int]]
    latency_ms: float
    interpreter: str
    ollama_tokens: int
    baseline_action: Action
    artifacts: dict = field(default_factory=dict)
