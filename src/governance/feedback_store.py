from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from governance.phase13_contracts import (
    AnalystFeedbackEvent,
)
from investigation.phase12_audit import (
    append_hash_chained_record,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "governance"
    / "phase13_feedback.duckdb"
)

DEFAULT_AUDIT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "feedback_audit_chain.jsonl"
)


class Phase13FeedbackStore:
    """
    Append-only human feedback store.

    Feedback is not automatically converted into a training label.
    Only separately adjudicated feedback may be marked modeling_eligible.
    No update/delete methods are exposed.
    """

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        audit_path: Path = DEFAULT_AUDIT_PATH,
    ) -> None:
        self.db_path = Path(db_path)
        self.audit_path = Path(audit_path)

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._initialize()

    def _connect(self):
        return duckdb.connect(
            str(self.db_path)
        )

    def _initialize(self) -> None:
        con = self._connect()

        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS analyst_feedback (
                    feedback_id VARCHAR PRIMARY KEY,
                    case_id VARCHAR NOT NULL,
                    transaction_id VARCHAR,
                    analyst_outcome VARCHAR NOT NULL,
                    confidence DOUBLE NOT NULL,
                    rationale VARCHAR NOT NULL,
                    analyst_id VARCHAR NOT NULL,
                    reviewer_id VARCHAR,
                    adjudication_status VARCHAR NOT NULL,
                    modeling_eligible BOOLEAN NOT NULL,
                    model_version VARCHAR NOT NULL,
                    explanation_version VARCHAR NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        finally:
            con.close()

    def add_feedback(
        self,
        *,
        case_id: str,
        analyst_outcome: str,
        confidence: float,
        rationale: str,
        analyst_id: str,
        transaction_id: str | None = None,
        reviewer_id: str | None = None,
        adjudication_status: str = "pending",
        modeling_eligible: bool = False,
        model_version: str = "graphshield-v2-phase10-certified",
        explanation_version: str = "phase11_explanation_bundle_v1",
    ) -> AnalystFeedbackEvent:
        event = AnalystFeedbackEvent(
            feedback_id=str(
                uuid.uuid4()
            ),
            case_id=case_id,
            transaction_id=transaction_id,
            analyst_outcome=analyst_outcome,
            confidence=confidence,
            rationale=rationale,
            analyst_id=analyst_id,
            reviewer_id=reviewer_id,
            adjudication_status=adjudication_status,
            modeling_eligible=modeling_eligible,
            model_version=model_version,
            explanation_version=explanation_version,
            created_at=datetime.now(
                timezone.utc
            ),
        )

        con = self._connect()

        try:
            con.execute(
                """
                INSERT INTO analyst_feedback
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    event.feedback_id,
                    event.case_id,
                    event.transaction_id,
                    event.analyst_outcome,
                    event.confidence,
                    event.rationale,
                    event.analyst_id,
                    event.reviewer_id,
                    event.adjudication_status,
                    event.modeling_eligible,
                    event.model_version,
                    event.explanation_version,
                    event.created_at,
                ],
            )
        finally:
            con.close()

        append_hash_chained_record(
            self.audit_path,
            {
                "event_type":
                    "ANALYST_FEEDBACK_APPENDED",
                "feedback":
                    event.model_dump(
                        mode="json"
                    ),
            },
        )

        return event

    def list_case_feedback(
        self,
        case_id: str,
    ) -> list[dict]:
        con = self._connect()

        try:
            rows = con.execute(
                """
                SELECT
                    feedback_id,
                    case_id,
                    transaction_id,
                    analyst_outcome,
                    confidence,
                    rationale,
                    analyst_id,
                    reviewer_id,
                    adjudication_status,
                    modeling_eligible,
                    model_version,
                    explanation_version,
                    created_at
                FROM analyst_feedback
                WHERE case_id = ?
                ORDER BY created_at ASC
                """,
                [case_id],
            ).fetchdf()
        finally:
            con.close()

        return json.loads(
            rows.to_json(
                orient="records",
                date_format="iso",
            )
        )

    def modeling_eligible_feedback(
        self,
    ) -> list[dict]:
        con = self._connect()

        try:
            rows = con.execute(
                """
                SELECT *
                FROM analyst_feedback
                WHERE modeling_eligible = TRUE
                  AND adjudication_status = 'adjudicated'
                ORDER BY created_at ASC
                """
            ).fetchdf()
        finally:
            con.close()

        return json.loads(
            rows.to_json(
                orient="records",
                date_format="iso",
            )
        )
