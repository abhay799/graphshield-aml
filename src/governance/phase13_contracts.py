from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AnalystOutcome = Literal[
    "escalate_review",
    "dismiss_alert",
    "needs_more_information",
    "monitor",
    "other",
]

AdjudicationStatus = Literal[
    "pending",
    "reviewed",
    "adjudicated",
]

DriftSeverity = Literal[
    "stable",
    "warning",
    "critical",
]


class AnalystFeedbackEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: str
    case_id: str = Field(min_length=1)
    transaction_id: str | None = None

    analyst_outcome: AnalystOutcome
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=4000)

    analyst_id: str = Field(min_length=1)
    reviewer_id: str | None = None

    adjudication_status: AdjudicationStatus = "pending"
    modeling_eligible: bool = False

    model_version: str = "graphshield-v2-phase10-certified"
    explanation_version: str = "phase11_explanation_bundle_v1"

    created_at: datetime

    @model_validator(mode="after")
    def validate_modeling_eligibility(self):
        if (
            self.modeling_eligible
            and self.adjudication_status != "adjudicated"
        ):
            raise ValueError(
                "modeling_eligible=True requires "
                "adjudication_status='adjudicated'."
            )

        if (
            self.adjudication_status == "adjudicated"
            and not self.reviewer_id
        ):
            raise ValueError(
                "Adjudicated feedback requires reviewer_id."
            )

        return self


class FeatureDriftMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str
    feature_type: Literal[
        "numeric",
        "categorical",
    ]

    metric_name: Literal[
        "psi",
        "total_variation_distance",
    ]

    metric_value: float = Field(ge=0.0)
    missing_rate_reference: float = Field(ge=0.0, le=1.0)
    missing_rate_monitor: float = Field(ge=0.0, le=1.0)
    missing_rate_delta: float

    unseen_category_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    severity: DriftSeverity


class DriftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[
        "phase13_drift_report_v1"
    ] = "phase13_drift_report_v1"

    reference_split: str
    monitor_split: str

    reference_rows: int = Field(ge=1)
    monitor_rows: int = Field(ge=1)

    feature_metrics: list[FeatureDriftMetric]
    overall_severity: DriftSeverity

    automatic_retraining_triggered: Literal[False] = False
    human_review_required: Literal[True] = True
    certified_models_modified: Literal[False] = False
