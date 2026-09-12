from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DRIFT_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "feature_drift_v1_report.json"
)

ALERT_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "drift_alerts_v1_report.json"
)


TEMPORAL_CONTEXT_FEATURES = {
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "sender_seconds_since_previous",
    "receiver_seconds_since_previous",
    "pair_seconds_since_previous",
    "pair_relationship_age_seconds",
    "reverse_pair_seconds_since_previous",
    "seconds_since_last_inbound_1h",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def build_drift_alerts() -> dict[str, Any]:
    report = _load_json(
        DRIFT_REPORT
    )

    critical = []
    warnings = []

    for item in report.get(
        "feature_metrics",
        [],
    ):
        enriched = {
            **item,
            "context": (
                "temporal_or_age_feature"
                if item.get("feature")
                in TEMPORAL_CONTEXT_FEATURES
                else "general_model_feature"
            ),
        }

        severity = item.get(
            "severity"
        )

        if severity == "critical":
            critical.append(
                enriched
            )
        elif severity == "warning":
            warnings.append(
                enriched
            )

    output = {
        "schema_version":
            "phase13_drift_alerts_v1",

        "overall_severity":
            report.get(
                "overall_severity"
            ),

        "critical_feature_count":
            len(
                critical
            ),

        "warning_feature_count":
            len(
                warnings
            ),

        "critical_features":
            critical,

        "warning_features":
            warnings,

        "governance_action": (
            "human_review_required"
            if critical
            or warnings
            else "continue_monitoring"
        ),

        "automatic_retraining_triggered":
            False,

        "automatic_model_promotion":
            False,

        "certified_models_modified":
            False,

        "interpretation": {
            "drift_is_not_model_failure":
                True,

            "temporal_progression_can_create_real_distribution_shift":
                True,

            "critical_drift_requires_review_not_automatic_retraining":
                True,
        },
    }

    ALERT_REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ALERT_REPORT.write_text(
        json.dumps(
            output,
            indent=2,
        ),
        encoding="utf-8",
    )

    return output


def main() -> None:
    result = build_drift_alerts()

    print(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        "GRAPHSHIELD_PHASE13_DRIFT_ALERTS=PASS"
    )


if __name__ == "__main__":
    main()
