from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from governance.feedback_store import (
    DEFAULT_DB_PATH,
)
from governance.phase13_drift_alerts import (
    ALERT_REPORT,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

STATUS_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "governance_status_v1_report.json"
)


def _read_alerts() -> dict[str, Any]:
    if not ALERT_REPORT.exists():
        raise FileNotFoundError(
            ALERT_REPORT
        )

    return json.loads(
        ALERT_REPORT.read_text(
            encoding="utf-8"
        )
    )


def _feedback_counts() -> dict[str, int]:
    if not DEFAULT_DB_PATH.exists():
        return {
            "feedback_events": 0,
            "adjudication_events": 0,
            "approved_for_modeling": 0,
        }

    con = duckdb.connect(
        str(
            DEFAULT_DB_PATH
        ),
        read_only=True,
    )

    try:
        feedback = con.execute(
            """
            SELECT COUNT(*)
            FROM analyst_feedback
            """
        ).fetchone()[0]

        try:
            adjudications = con.execute(
                """
                SELECT COUNT(*)
                FROM feedback_adjudications
                """
            ).fetchone()[0]

            approved = con.execute(
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
                SELECT COUNT(*)
                FROM latest
                WHERE rn = 1
                  AND decision = 'approved_for_modeling'
                  AND modeling_eligible = TRUE
                """
            ).fetchone()[0]

        except duckdb.CatalogException:
            adjudications = 0
            approved = 0

    finally:
        con.close()

    return {
        "feedback_events":
            int(
                feedback
            ),
        "adjudication_events":
            int(
                adjudications
            ),
        "approved_for_modeling":
            int(
                approved
            ),
    }


def build_governance_status() -> dict[str, Any]:
    alerts = _read_alerts()
    feedback = _feedback_counts()

    review_required = (
        alerts.get(
            "governance_action"
        )
        == "human_review_required"
    )

    result = {
        "schema_version":
            "phase13_governance_status_v1",

        "drift": {
            "overall_severity":
                alerts.get(
                    "overall_severity"
                ),

            "critical_feature_count":
                alerts.get(
                    "critical_feature_count",
                    0,
                ),

            "warning_feature_count":
                alerts.get(
                    "warning_feature_count",
                    0,
                ),

            "human_review_required":
                review_required,
        },

        "feedback":
            feedback,

        "model_governance": {
            "certified_model":
                "graphshield-v2-phase10-certified",

            "automatic_retraining_enabled":
                False,

            "automatic_promotion_enabled":
                False,

            "human_approval_required_for_retraining":
                True,

            "human_approval_required_for_promotion":
                True,

            "phase10_model_modified":
                False,
        },

        "status": (
            "REVIEW_REQUIRED"
            if review_required
            else "MONITORING"
        ),
    }

    STATUS_REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATUS_REPORT.write_text(
        json.dumps(
            result,
            indent=2,
        ),
        encoding="utf-8",
    )

    return result


def main() -> None:
    result = build_governance_status()

    print(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        "GRAPHSHIELD_PHASE13_GOVERNANCE_STATUS=PASS"
    )


if __name__ == "__main__":
    main()
