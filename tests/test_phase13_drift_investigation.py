from __future__ import annotations

import json
from pathlib import Path

from governance.phase13_drift_investigation import (
    build_drift_investigation,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_drift_investigation_ranks_and_preserves_governance(
    tmp_path: Path,
) -> None:
    alerts = {
        "overall_severity": "critical",
        "critical_features": [
            {
                "feature": "pair_relationship_age_seconds",
                "feature_type": "numeric",
                "metric_name": "psi",
                "metric_value": 8.2,
                "missing_rate_reference": 0.0,
                "missing_rate_monitor": 0.0,
                "missing_rate_delta": 0.0,
                "unseen_category_rate": None,
                "severity": "critical",
            },
            {
                "feature": "receiver_prior_tx_count",
                "feature_type": "numeric",
                "metric_name": "psi",
                "metric_value": 0.63,
                "missing_rate_reference": 0.0,
                "missing_rate_monitor": 0.0,
                "missing_rate_delta": 0.0,
                "unseen_category_rate": None,
                "severity": "critical",
            },
        ],
        "warning_features": [
            {
                "feature": "sender_fanout_ratio_24h",
                "feature_type": "numeric",
                "metric_name": "psi",
                "metric_value": 0.18,
                "missing_rate_reference": 0.0,
                "missing_rate_monitor": 0.0,
                "missing_rate_delta": 0.0,
                "unseen_category_rate": None,
                "severity": "warning",
            }
        ],
    }
    score = {
        "overall_severity": "stable",
    }

    alert_path = tmp_path / "alerts.json"
    score_path = tmp_path / "score.json"
    output_path = tmp_path / "investigation.json"

    _write(alert_path, alerts)
    _write(score_path, score)

    result = build_drift_investigation(
        alert_report_path=alert_path,
        score_drift_report_path=score_path,
        output_path=output_path,
    )

    assert output_path.exists()
    assert result["feature_drift_severity"] == "critical"
    assert result["score_drift_severity"] == "stable"

    ranked = result["ranked_features"]
    assert ranked[0]["feature"] == "pair_relationship_age_seconds"
    assert ranked[1]["feature"] == "receiver_prior_tx_count"
    assert ranked[2]["severity"] == "warning"

    governance = result["governance"]
    assert governance["human_review_required"] is True
    assert governance["automatic_retraining_triggered"] is False
    assert governance["automatic_recalibration_triggered"] is False
    assert governance["automatic_model_promotion"] is False
    assert governance["automatic_threshold_change"] is False
    assert governance["certified_phase10_model_modified"] is False
    assert governance["test_used_for_model_selection"] is False


def test_drift_investigation_marks_hypotheses_non_causal(
    tmp_path: Path,
) -> None:
    alerts = {
        "overall_severity": "warning",
        "critical_features": [],
        "warning_features": [
            {
                "feature": "seconds_since_last_inbound_1h",
                "feature_type": "numeric",
                "metric_name": "psi",
                "metric_value": 0.14,
                "missing_rate_reference": 0.98,
                "missing_rate_monitor": 0.95,
                "missing_rate_delta": -0.03,
                "unseen_category_rate": None,
                "severity": "warning",
            }
        ],
    }
    score = {
        "overall_severity": "stable",
    }

    alert_path = tmp_path / "alerts.json"
    score_path = tmp_path / "score.json"
    output_path = tmp_path / "investigation.json"

    _write(alert_path, alerts)
    _write(score_path, score)

    result = build_drift_investigation(
        alert_report_path=alert_path,
        score_drift_report_path=score_path,
        output_path=output_path,
    )

    row = result["ranked_features"][0]
    assert row["monitoring_domain"] == "temporal_progression"
    assert any(
        "causality is not asserted" in item
        for item in row["investigation_hypotheses"]
    )
    assert result["governance"]["hypotheses_are_not_causal_claims"] is True
