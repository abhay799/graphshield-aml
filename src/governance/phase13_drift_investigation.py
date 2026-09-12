from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ALERT_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "drift_alerts_v1_report.json"
)

SCORE_DRIFT_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "score_drift_v1_report.json"
)

INVESTIGATION_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "drift_investigation_v1_report.json"
)

_SEVERITY_RANK = {
    "critical": 0,
    "warning": 1,
    "stable": 2,
    "unknown": 3,
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Required Phase 13 report not found: {path}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _feature_domain(feature: str) -> str:
    name = feature.lower()

    if any(
        token in name
        for token in (
            "hour",
            "second",
            "time",
            "age",
            "day",
            "date",
            "previous",
        )
    ):
        return "temporal_progression"

    if any(
        token in name
        for token in (
            "pair_",
            "counterparty",
            "bank_pair",
            "relationship",
        )
    ):
        return "relationship_history"

    if any(
        token in name
        for token in (
            "unique_sender",
            "unique_receiver",
            "degree",
            "bridge",
            "fanout",
            "fanin",
            "neighbor",
            "community",
            "graph",
        )
    ):
        return "graph_or_network_behavior"

    if any(
        token in name
        for token in (
            "count",
            "velocity",
            "_1h",
            "_24h",
            "_7d",
            "_30d",
        )
    ):
        return "transaction_history_or_velocity"

    return "general_model_feature"


def _hypotheses(
    feature: str,
    domain: str,
    item: dict[str, Any],
) -> list[str]:
    hypotheses: list[str] = []

    if domain == "temporal_progression":
        hypotheses.append(
            "Chronological progression between validation and the "
            "post-lock monitoring window may shift this feature naturally."
        )
    elif domain == "relationship_history":
        hypotheses.append(
            "Accumulating sender/receiver or pair history may change "
            "relationship-level distributions over time."
        )
    elif domain == "graph_or_network_behavior":
        hypotheses.append(
            "Network connectivity or counterparty-mix changes may alter "
            "graph-derived behavior without implying model failure."
        )
    elif domain == "transaction_history_or_velocity":
        hypotheses.append(
            "Transaction-volume, velocity, or rolling-history changes may "
            "reflect genuine population or activity-pattern shift."
        )
    else:
        hypotheses.append(
            "The monitored population distribution changed relative to "
            "the frozen validation reference and requires analyst review."
        )

    missing_delta = item.get("missing_rate_delta")
    if isinstance(missing_delta, (int, float)) and abs(missing_delta) >= 0.02:
        hypotheses.append(
            "Missingness changed materially and should be checked for "
            "upstream data-quality or feature-generation changes."
        )

    unseen_rate = item.get("unseen_category_rate")
    if isinstance(unseen_rate, (int, float)) and unseen_rate > 0:
        hypotheses.append(
            "Previously unseen categorical values appeared in monitoring "
            "data and should be reviewed for schema/population change."
        )

    hypotheses.append(
        "These are monitoring hypotheses only; causality is not asserted."
    )
    return hypotheses


def _review_checks(
    domain: str,
    item: dict[str, Any],
) -> list[str]:
    checks = [
        "Verify source-data/schema consistency for this feature.",
        "Compare validation and monitoring-window descriptive statistics.",
        "Check whether the shift is expected from chronological progression.",
    ]

    if domain == "relationship_history":
        checks.append(
            "Inspect pair/counterparty history accumulation and cohort mix."
        )
    elif domain == "graph_or_network_behavior":
        checks.append(
            "Inspect network-degree, counterparty-mix, and graph-structure changes."
        )
    elif domain == "transaction_history_or_velocity":
        checks.append(
            "Inspect transaction-volume and rolling-window population changes."
        )
    elif domain == "temporal_progression":
        checks.append(
            "Inspect timestamp coverage and age/time-derived feature semantics."
        )

    missing_delta = item.get("missing_rate_delta")
    if isinstance(missing_delta, (int, float)) and abs(missing_delta) >= 0.02:
        checks.append(
            "Investigate the missing-rate change before drawing model conclusions."
        )

    return checks


def _normalize_feature(
    item: dict[str, Any],
) -> dict[str, Any]:
    feature = str(item.get("feature", "unknown_feature"))
    severity = str(item.get("severity", "unknown"))
    domain = _feature_domain(feature)

    return {
        "feature": feature,
        "severity": severity,
        "feature_type": item.get("feature_type"),
        "metric_name": item.get("metric_name"),
        "metric_value": item.get("metric_value"),
        "monitoring_domain": domain,
        "missing_rate_reference": item.get("missing_rate_reference"),
        "missing_rate_monitor": item.get("missing_rate_monitor"),
        "missing_rate_delta": item.get("missing_rate_delta"),
        "unseen_category_rate": item.get("unseen_category_rate"),
        "investigation_hypotheses": _hypotheses(
            feature,
            domain,
            item,
        ),
        "recommended_review_checks": _review_checks(
            domain,
            item,
        ),
    }


def build_drift_investigation(
    *,
    alert_report_path: Path = ALERT_REPORT,
    score_drift_report_path: Path = SCORE_DRIFT_REPORT,
    output_path: Path = INVESTIGATION_REPORT,
) -> dict[str, Any]:
    alerts = _load_json(alert_report_path)
    score_drift = _load_json(score_drift_report_path)

    candidates = [
        *alerts.get("critical_features", []),
        *alerts.get("warning_features", []),
    ]

    ranked = [
        _normalize_feature(item)
        for item in candidates
    ]

    ranked.sort(
        key=lambda row: (
            _SEVERITY_RANK.get(
                str(row.get("severity", "unknown")),
                99,
            ),
            -float(row.get("metric_value") or 0.0),
            str(row.get("feature", "")),
        )
    )

    by_domain: dict[str, int] = {}
    for row in ranked:
        domain = str(row["monitoring_domain"])
        by_domain[domain] = by_domain.get(domain, 0) + 1

    feature_severity = str(
        alerts.get("overall_severity", "unknown")
    )
    score_severity = str(
        score_drift.get("overall_severity", "unknown")
    )

    output = {
        "schema_version": "phase13_drift_investigation_v1",
        "feature_drift_severity": feature_severity,
        "score_drift_severity": score_severity,
        "feature_score_relationship": {
            "feature_drift_and_score_drift_may_differ": True,
            "current_interpretation": (
                "Input/feature distributions changed while the frozen "
                "model score distribution may remain comparatively stable."
                if feature_severity in {"warning", "critical"}
                and score_severity == "stable"
                else
                "Feature and score drift should be reviewed independently."
            ),
            "model_failure_inferred_from_feature_drift": False,
        },
        "ranked_features": ranked,
        "monitoring_domain_counts": dict(
            sorted(
                by_domain.items(),
                key=lambda kv: (-kv[1], kv[0]),
            )
        ),
        "governance": {
            "human_review_required": (
                feature_severity in {"warning", "critical"}
                or score_severity in {"warning", "critical"}
            ),
            "automatic_retraining_triggered": False,
            "automatic_recalibration_triggered": False,
            "automatic_model_promotion": False,
            "automatic_threshold_change": False,
            "certified_phase10_model_modified": False,
            "test_used_for_model_selection": False,
            "investigation_is_diagnostic_only": True,
            "hypotheses_are_not_causal_claims": True,
        },
        "recommended_next_action": (
            "human_drift_investigation"
            if feature_severity in {"warning", "critical"}
            or score_severity in {"warning", "critical"}
            else "continue_monitoring"
        ),
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_text(
        json.dumps(
            output,
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def main() -> None:
    result = build_drift_investigation()

    print(
        json.dumps(
            {
                "schema_version": result["schema_version"],
                "feature_drift_severity": (
                    result["feature_drift_severity"]
                ),
                "score_drift_severity": (
                    result["score_drift_severity"]
                ),
                "ranked_feature_count": len(
                    result["ranked_features"]
                ),
                "monitoring_domain_counts": (
                    result["monitoring_domain_counts"]
                ),
                "recommended_next_action": (
                    result["recommended_next_action"]
                ),
                "governance": result["governance"],
            },
            indent=2,
        )
    )
    print(
        "GRAPHSHIELD_PHASE13_DRIFT_INVESTIGATION=PASS"
    )


if __name__ == "__main__":
    main()
