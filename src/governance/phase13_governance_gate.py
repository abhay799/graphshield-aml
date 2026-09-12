from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from governance.feedback_store import (
    Phase13FeedbackStore,
)


FEATURE_DRIFT_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "feature_drift_v1_report.json"
)

SCORE_DRIFT_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "score_drift_v1_report.json"
)

GATE_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "governance_gate_v1_report.json"
)


def _load_json(
    path: Path,
) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            path
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def evaluate_governance_gate(
    *,
    feature_severity: str,
    score_severity: str,
    eligible_feedback_count: int,
    minimum_feedback_for_retraining_review: int = 100,
) -> dict:
    severities = {
        feature_severity,
        score_severity,
    }

    critical = (
        "critical"
        in severities
    )

    warning = (
        "warning"
        in severities
    )

    enough_feedback = (
        eligible_feedback_count
        >= minimum_feedback_for_retraining_review
    )

    if critical:
        recommended_action = (
            "investigate_critical_drift"
        )
    elif warning:
        recommended_action = (
            "investigate_drift"
        )
    else:
        recommended_action = (
            "continue_monitoring"
        )

    if (
        (critical or warning)
        and enough_feedback
    ):
        recommended_action = (
            "prepare_human_retraining_review"
        )

    return {
        "feature_drift_severity":
            feature_severity,

        "score_drift_severity":
            score_severity,

        "eligible_feedback_count":
            eligible_feedback_count,

        "minimum_feedback_for_retraining_review":
            minimum_feedback_for_retraining_review,

        "enough_adjudicated_feedback_for_review":
            enough_feedback,

        "drift_review_required":
            critical
            or warning,

        "retraining_review_may_be_prepared":
            (
                enough_feedback
                and (
                    critical
                    or warning
                )
            ),

        "recommended_action":
            recommended_action,

        "automatic_retraining_allowed":
            False,

        "automatic_model_promotion_allowed":
            False,

        "automatic_threshold_change_allowed":
            False,

        "human_approval_required":
            True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--minimum-feedback",
        type=int,
        default=100,
    )

    args = parser.parse_args()

    feature = _load_json(
        FEATURE_DRIFT_REPORT
    )

    score = _load_json(
        SCORE_DRIFT_REPORT
    )

    eligible_feedback = (
        Phase13FeedbackStore()
        .modeling_eligible_feedback()
    )

    gate = evaluate_governance_gate(
        feature_severity=
            feature[
                "overall_severity"
            ],

        score_severity=
            score[
                "overall_severity"
            ],

        eligible_feedback_count=
            len(
                eligible_feedback
            ),

        minimum_feedback_for_retraining_review=
            args.minimum_feedback,
    )

    report = {
        "schema_version":
            "phase13_governance_gate_v1",

        "status":
            "PASS",

        "feature_drift_report":
            str(
                FEATURE_DRIFT_REPORT
            ),

        "score_drift_report":
            str(
                SCORE_DRIFT_REPORT
            ),

        "gate":
            gate,

        "governance": {
            "feedback_is_not_automatically_a_label":
                True,

            "adjudicated_feedback_only_for_modeling":
                True,

            "automatic_retraining":
                False,

            "automatic_model_promotion":
                False,

            "human_review_required":
                True,

            "certified_phase10_model":
                "read_only",
        },
    }

    GATE_REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    GATE_REPORT.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            report,
            indent=2,
        )
    )

    print(
        "GRAPHSHIELD_PHASE13_GOVERNANCE_GATE=PASS"
    )


if __name__ == "__main__":
    main()
