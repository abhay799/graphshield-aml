from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ToolName = Literal[
    "case_overview",
    "search_evidence",
    "path_evidence",
    "history_evidence",
    "policy_search",
    "phase11_explanation",
]

RunStatus = Literal[
    "planned",
    "running",
    "completed",
    "failed",
]


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: ToolName
    case_id: str = Field(min_length=1)
    query: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class ToolCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: ToolName
    success: bool
    case_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    payload: Any = None
    error: str | None = None
    latency_ms: float = Field(ge=0.0)


class InvestigationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    question: str
    planned_tools: list[ToolName]
    max_tool_calls: int = Field(ge=1, le=8)
    include_policy: bool
    rationale: list[str] = Field(default_factory=list)


class ContradictionFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_type: Literal[
        "supporting",
        "countervailing",
        "insufficient",
    ]
    title: str
    evidence_refs: list[str] = Field(default_factory=list)
    detail: str


class InvestigationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[
        "phase12_investigation_result_v1"
    ] = "phase12_investigation_result_v1"

    run_id: str
    case_id: str
    question: str
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None

    plan: InvestigationPlan
    tool_results: list[ToolCallResult] = Field(
        default_factory=list
    )
    retrieved_evidence_ids: list[str] = Field(
        default_factory=list
    )
    contradictions: list[ContradictionFinding] = Field(
        default_factory=list
    )

    answer: str | None = None
    cited_ids: list[str] = Field(default_factory=list)
    citation_validation_passed: bool = False
    grounding_validation: dict[str, Any] = Field(
        default_factory=dict
    )
    answer_withheld: bool = False
    failure_reason: str | None = None

    governance: dict[str, Any] = Field(
        default_factory=lambda: {
            "mode": "decision_support_only",
            "human_review_required": True,
            "read_only_tools_only": True,
            "fail_closed_on_grounding_failure": True,
            "autonomous_account_blocking": False,
            "autonomous_case_closure": False,
            "autonomous_regulatory_filing": False,
        }
    )
