from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHASE13_DIR = PROJECT_ROOT / "reports" / "v2" / "phase13"

GATE_REPORT = PHASE13_DIR / "governance_gate_v1_report.json"
STATUS_REPORT = PHASE13_DIR / "governance_status_v1_report.json"
INVESTIGATION_REPORT = PHASE13_DIR / "drift_investigation_v1_report.json"
PERFORMANCE_REPORT = PHASE13_DIR / "performance_monitor_v1_report.json"
PROPOSAL_REPORT = PHASE13_DIR / "retraining_review_proposal_v1_report.json"


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required Phase 13 report missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _eligible_feedback_count(status: dict[str, Any], gate: dict[str, Any]) -> int:
    feedback = status.get("feedback", {})
    for key in ("approved_for_modeling", "modeling_eligible", "eligible_feedback_count"):
        value = feedback.get(key)
        if isinstance(value, int):
            return value
    value = gate.get("eligible_feedback_count")
    return int(value) if isinstance(value, int) else 0


def build_retraining_review_proposal(
    *,
    minimum_feedback: int = 100,
    gate_path: Path = GATE_REPORT,
    status_path: Path = STATUS_REPORT,
    investigation_path: Path = INVESTIGATION_REPORT,
    performance_path: Path = PERFORMANCE_REPORT,
    output_path: Path = PROPOSAL_REPORT,
) -> dict[str, Any]:
    gate = _read(gate_path)
    status = _read(status_path)
    investigation = _read(investigation_path)
    performance = _read(performance_path)

    eligible = _eligible_feedback_count(status, gate)
    enough_feedback = eligible >= minimum_feedback
    drift_requires_review = investigation.get("recommended_next_action") == "human_drift_investigation"
    valid_performance = performance.get("status") == "MONITORED"

    may_prepare = bool(enough_feedback and drift_requires_review)
    report = {
        "schema_version": "phase13_retraining_review_proposal_v1",
        "proposal_status": "READY_FOR_HUMAN_REVIEW" if may_prepare else "NOT_READY",
        "eligible_feedback_count": eligible,
        "minimum_feedback_required": minimum_feedback,
        "enough_adjudicated_feedback": enough_feedback,
        "drift_review_required": drift_requires_review,
        "validated_performance_monitoring_available": valid_performance,
        "retraining_review_may_be_prepared": may_prepare,
        "human_approval": {
            "required": True,
            "received": False,
        },
        "proposal_only": True,
        "execution": {
            "training_started": False,
            "recalibration_started": False,
            "model_promotion_started": False,
            "threshold_change_started": False,
        },
        "governance": {
            "automatic_retraining_allowed": False,
            "automatic_recalibration_allowed": False,
            "automatic_model_promotion_allowed": False,
            "automatic_threshold_change_allowed": False,
            "certified_phase10_model_read_only": True,
            "test_used_for_model_selection": False,
        },
        "recommended_action": (
            "collect_and_adjudicate_more_feedback"
            if not enough_feedback
            else "human_review_of_retraining_proposal"
        ),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-feedback", type=int, default=100)
    args = parser.parse_args()
    report = build_retraining_review_proposal(minimum_feedback=args.minimum_feedback)
    print(json.dumps(report, indent=2))
    print("GRAPHSHIELD_PHASE13_RETRAINING_PROPOSAL=PASS")


if __name__ == "__main__":
    main()
