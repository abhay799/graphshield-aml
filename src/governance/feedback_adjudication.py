from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from governance.feedback_store import (
    DEFAULT_DB_PATH,
)
from investigation.phase12_audit import (
    append_hash_chained_record,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ADJUDICATION_AUDIT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "feedback_adjudication_audit_chain.jsonl"
)


class FeedbackAdjudicationEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    adjudication_id: str
    feedback_id: str = Field(
        min_length=1
    )
    reviewer_id: str = Field(
        min_length=1
    )

    decision: str = Field(
        pattern=(
            "^(approved_for_modeling|"
            "rejected_for_modeling|"
            "needs_more_review)$"
        )
    )

    rationale: str = Field(
        min_length=1,
        max_length=4000,
    )

    modeling_eligible: bool
    created_at: datetime

    @model_validator(mode="after")
    def validate_decision(self):
        if (
            self.decision
            == "approved_for_modeling"
            and not self.modeling_eligible
        ):
            raise ValueError(
                "approved_for_modeling requires "
                "modeling_eligible=True."
            )

        if (
            self.decision
            != "approved_for_modeling"
            and self.modeling_eligible
        ):
            raise ValueError(
                "Only approved_for_modeling may set "
                "modeling_eligible=True."
            )

        return self


class Phase13FeedbackAdjudicationStore:
    """
    Append-only second-review workflow.

    Original analyst feedback rows are never updated.
    Modeling eligibility is derived from adjudication events.
    """

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        audit_path: Path = DEFAULT_ADJUDICATION_AUDIT,
    ) -> None:
        self.db_path = Path(
            db_path
        )
        self.audit_path = Path(
            audit_path
        )

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._initialize()

    def _connect(self):
        return duckdb.connect(
            str(
                self.db_path
            )
        )

    def _initialize(self) -> None:
        con = self._connect()

        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_adjudications (
                    adjudication_id VARCHAR PRIMARY KEY,
                    feedback_id VARCHAR NOT NULL,
                    reviewer_id VARCHAR NOT NULL,
                    decision VARCHAR NOT NULL,
                    rationale VARCHAR NOT NULL,
                    modeling_eligible BOOLEAN NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        finally:
            con.close()

    def _feedback_exists(
        self,
        feedback_id: str,
    ) -> bool:
        con = self._connect()

        try:
            row = con.execute(
                """
                SELECT COUNT(*)
                FROM analyst_feedback
                WHERE feedback_id = ?
                """,
                [feedback_id],
            ).fetchone()
        finally:
            con.close()

        return bool(
            row
            and row[0] > 0
        )

    def adjudicate(
        self,
        *,
        feedback_id: str,
        reviewer_id: str,
        decision: str,
        rationale: str,
    ) -> FeedbackAdjudicationEvent:
        if not self._feedback_exists(
            feedback_id
        ):
            raise KeyError(
                f"Unknown feedback_id: {feedback_id}"
            )

        event = FeedbackAdjudicationEvent(
            adjudication_id=str(
                uuid.uuid4()
            ),
            feedback_id=feedback_id,
            reviewer_id=reviewer_id,
            decision=decision,
            rationale=rationale,
            modeling_eligible=(
                decision
                == "approved_for_modeling"
            ),
            created_at=datetime.now(
                timezone.utc
            ),
        )

        con = self._connect()

        try:
            con.execute(
                """
                INSERT INTO feedback_adjudications
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    event.adjudication_id,
                    event.feedback_id,
                    event.reviewer_id,
                    event.decision,
                    event.rationale,
                    event.modeling_eligible,
                    event.created_at,
                ],
            )
        finally:
            con.close()

        append_hash_chained_record(
            self.audit_path,
            {
                "event_type":
                    "FEEDBACK_ADJUDICATION_APPENDED",

                "adjudication":
                    event.model_dump(
                        mode="json"
                    ),
            },
        )

        return event

    def latest_adjudication(
        self,
        feedback_id: str,
    ) -> dict | None:
        con = self._connect()

        try:
            row = con.execute(
                """
                SELECT
                    adjudication_id,
                    feedback_id,
                    reviewer_id,
                    decision,
                    rationale,
                    modeling_eligible,
                    created_at
                FROM feedback_adjudications
                WHERE feedback_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [feedback_id],
            ).fetchdf()
        finally:
            con.close()

        if row.empty:
            return None

        return json.loads(
            row.to_json(
                orient="records",
                date_format="iso",
            )
        )[0]

    def approved_feedback_ids(
        self,
    ) -> list[str]:
        con = self._connect()

        try:
            rows = con.execute(
                """
                WITH latest AS (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (
                            PARTITION BY feedback_id
                            ORDER BY created_at DESC
                        ) AS rn
                    FROM feedback_adjudications
                )
                SELECT feedback_id
                FROM latest
                WHERE rn = 1
                  AND decision = 'approved_for_modeling'
                  AND modeling_eligible = TRUE
                ORDER BY feedback_id
                """
            ).fetchall()
        finally:
            con.close()

        return [
            str(
                row[0]
            )
            for row in rows
        ]
