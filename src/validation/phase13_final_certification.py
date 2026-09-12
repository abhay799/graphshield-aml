from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = PROJECT_ROOT / "reports" / "v2" / "phase13"

REPORTS = {
    "feature_drift": REPORT_DIR / "feature_drift_v1_report.json",
    "score_drift": REPORT_DIR / "score_drift_v1_report.json",
    "drift_alerts": REPORT_DIR / "drift_alerts_v1_report.json",
    "drift_investigation": REPORT_DIR / "drift_investigation_v1_report.json",
    "governance_gate": REPORT_DIR / "governance_gate_v1_report.json",
    "governance_status": REPORT_DIR / "governance_status_v1_report.json",
    "performance": REPORT_DIR / "performance_monitor_v1_report.json",
    "retraining_proposal": REPORT_DIR / "retraining_review_proposal_v1_report.json",
}


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssertionError(f"Missing required Phase 13 report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _first_present(*candidates: tuple[dict[str, Any], str]) -> tuple[bool, Any]:
    for mapping, key in candidates:
        if isinstance(mapping, dict) and key in mapping:
            return True, mapping[key]
    return False, None


def _require_bool(
    description: str,
    expected: bool,
    *candidates: tuple[dict[str, Any], str],
) -> None:
    found, value = _first_present(*candidates)
    if not found:
        locations = ", ".join(key for _, key in candidates)
        raise AssertionError(
            f"Missing governance field for {description}; checked: {locations}"
        )
    if value is not expected:
        raise AssertionError(
            f"Expected {description}={str(expected).lower()}, got {value!r}"
        )


def _certify_reports() -> dict[str, Any]:
    r = {name: _read(path) for name, path in REPORTS.items()}

    feature = r["feature_drift"]
    score = r["score_drift"]
    alerts = r["drift_alerts"]
    investigation = r["drift_investigation"]
    gate = r["governance_gate"]
    status = r["governance_status"]
    performance = r["performance"]
    proposal = r["retraining_proposal"]

    valid_severities = {"stable", "warning", "critical"}

    if feature.get("overall_severity") not in valid_severities:
        raise AssertionError("Invalid feature drift severity.")
    if score.get("overall_severity") not in valid_severities:
        raise AssertionError("Invalid score drift severity.")

    # Feature drift report: current schema is top-level; nested fallback retained.
    feature_gov = feature.get("governance", {})
    _require_bool(
        "feature drift automatic retraining",
        False,
        (feature, "automatic_retraining_triggered"),
        (feature_gov, "automatic_retraining_triggered"),
    )
    _require_bool(
        "feature drift certified model modification",
        False,
        (feature, "certified_models_modified"),
        (feature_gov, "certified_models_modified"),
    )

    # Score drift report: current schema stores governance flags under governance.
    score_gov = score.get("governance", {})
    _require_bool(
        "score drift automatic retraining",
        False,
        (score_gov, "automatic_retraining_triggered"),
        (score, "automatic_retraining_triggered"),
    )
    _require_bool(
        "score drift automatic recalibration",
        False,
        (score_gov, "automatic_recalibration_triggered"),
        (score, "automatic_recalibration_triggered"),
    )
    _require_bool(
        "score drift automatic promotion",
        False,
        (score_gov, "automatic_model_promotion"),
        (score, "automatic_model_promotion"),
    )
    _require_bool(
        "test used for model selection",
        False,
        (score_gov, "test_used_for_model_selection"),
        (score, "test_used_for_model_selection"),
    )

    # Alert layer must remain diagnostic/governance-only.
    alerts_gov = alerts.get("governance", {})
    _require_bool(
        "drift alerts automatic retraining",
        False,
        (alerts, "automatic_retraining_triggered"),
        (alerts_gov, "automatic_retraining_triggered"),
    )
    _require_bool(
        "drift alerts automatic promotion",
        False,
        (alerts, "automatic_model_promotion"),
        (alerts_gov, "automatic_model_promotion"),
    )
    _require_bool(
        "drift alerts certified model modification",
        False,
        (alerts, "certified_models_modified"),
        (alerts_gov, "certified_models_modified"),
    )

    # Investigation layer.
    inv_gov = investigation.get("governance", {})
    for desc, key in (
        ("investigation automatic retraining", "automatic_retraining_triggered"),
        ("investigation automatic recalibration", "automatic_recalibration_triggered"),
        ("investigation automatic promotion", "automatic_model_promotion"),
        ("investigation automatic threshold change", "automatic_threshold_change"),
        ("investigation Phase 10 modification", "certified_phase10_model_modified"),
        ("investigation test used for model selection", "test_used_for_model_selection"),
    ):
        _require_bool(desc, False, (inv_gov, key))

    _require_bool(
        "investigation diagnostic-only boundary",
        True,
        (inv_gov, "investigation_is_diagnostic_only"),
    )
    _require_bool(
        "non-causal drift hypotheses boundary",
        True,
        (inv_gov, "hypotheses_are_not_causal_claims"),
    )

    # Governance gate: support both existing top-level and nested governance schemas.
    if gate.get("status") != "PASS":
        raise AssertionError(
            f"Governance gate status must be PASS, got {gate.get('status')!r}"
        )

    gate_gov = gate.get("governance", {})
    _require_bool(
        "governance gate automatic retraining",
        False,
        (gate, "automatic_retraining_allowed"),
        (gate_gov, "automatic_retraining"),
        (gate_gov, "automatic_retraining_allowed"),
    )
    _require_bool(
        "governance gate automatic promotion",
        False,
        (gate, "automatic_model_promotion_allowed"),
        (gate_gov, "automatic_model_promotion"),
        (gate_gov, "automatic_model_promotion_allowed"),
    )
    # Threshold-change prohibition is enforced by downstream Phase 13
    # investigation/performance/proposal governance. Some existing gate
    # report versions do not emit a threshold field, so validate it only
    # when the field is present rather than requiring schema presence.
    threshold_candidates = [
        (gate, "automatic_threshold_change_allowed"),
        (gate_gov, "automatic_threshold_change"),
        (gate_gov, "automatic_threshold_change_allowed"),
    ]
    threshold_found, threshold_value = _first_present(*threshold_candidates)
    if threshold_found and threshold_value is not False:
        raise AssertionError(
            f"Expected governance gate automatic threshold change=false, "
            f"got {threshold_value!r}"
        )
    _require_bool(
        "governance gate human review/approval requirement",
        True,
        (gate, "human_approval_required"),
        (gate, "human_review_required"),
        (gate_gov, "human_approval_required"),
        (gate_gov, "human_review_required"),
    )

    # Governance status report.
    model_gov = status.get("model_governance", {})
    _require_bool(
        "status automatic retraining enabled",
        False,
        (model_gov, "automatic_retraining_enabled"),
    )
    _require_bool(
        "status automatic promotion enabled",
        False,
        (model_gov, "automatic_promotion_enabled"),
    )
    _require_bool(
        "status Phase 10 model modified",
        False,
        (model_gov, "phase10_model_modified"),
    )
    _require_bool(
        "human approval required for retraining",
        True,
        (model_gov, "human_approval_required_for_retraining"),
    )
    _require_bool(
        "human approval required for promotion",
        True,
        (model_gov, "human_approval_required_for_promotion"),
    )

    # Performance monitoring must never treat raw analyst feedback as truth.
    perf_gov = performance.get("governance", {})
    for desc, key in (
        ("performance automatic retraining", "automatic_retraining_triggered"),
        ("performance automatic recalibration", "automatic_recalibration_triggered"),
        ("performance automatic promotion", "automatic_model_promotion"),
        ("performance automatic threshold change", "automatic_threshold_change"),
        ("performance Phase 10 modification", "certified_phase10_model_modified"),
    ):
        _require_bool(desc, False, (perf_gov, key))

    label_contract = performance.get("label_contract", {})
    _require_bool(
        "analyst feedback is not ground truth",
        True,
        (label_contract, "analyst_feedback_is_not_ground_truth"),
    )
    _require_bool(
        "only adjudicated/authoritative outcomes are eligible",
        True,
        (label_contract, "only_adjudicated_or_authoritative_outcomes_are_eligible"),
    )

    # Retraining artifact is proposal-only and execution must remain off.
    execution = proposal.get("execution", {})
    for desc, key in (
        ("training started", "training_started"),
        ("recalibration started", "recalibration_started"),
        ("promotion started", "model_promotion_started"),
        ("threshold change started", "threshold_change_started"),
    ):
        _require_bool(desc, False, (execution, key))

    proposal_gov = proposal.get("governance", {})
    for desc, key in (
        ("proposal automatic retraining allowed", "automatic_retraining_allowed"),
        ("proposal automatic recalibration allowed", "automatic_recalibration_allowed"),
        ("proposal automatic promotion allowed", "automatic_model_promotion_allowed"),
        ("proposal automatic threshold change allowed", "automatic_threshold_change_allowed"),
        ("proposal test used for model selection", "test_used_for_model_selection"),
    ):
        _require_bool(desc, False, (proposal_gov, key))

    _require_bool(
        "retraining artifact proposal-only",
        True,
        (proposal, "proposal_only"),
    )
    _require_bool(
        "proposal human approval required",
        True,
        (proposal.get("human_approval", {}), "required"),
    )

    eligible = int(proposal.get("eligible_feedback_count", 0))
    minimum = int(proposal.get("minimum_feedback_required", 100))
    may_prepare = bool(proposal.get("retraining_review_may_be_prepared", False))

    if eligible < minimum and may_prepare:
        raise AssertionError(
            "Retraining review cannot be prepared below the minimum "
            "eligible-feedback count."
        )

    return {
        "feature_drift_severity": feature.get("overall_severity"),
        "score_drift_severity": score.get("overall_severity"),
        "eligible_feedback_count": eligible,
        "minimum_feedback_required": minimum,
        "retraining_review_may_be_prepared": may_prepare,
        "performance_status": performance.get("status"),
        "governance_status": status.get("status"),
        "governance_gate_status": gate.get("status"),
    }


def _certify_api() -> list[str]:
    # Verify the Phase 13 router itself exposes the required endpoints.
    from api.phase13_routes import router as phase13_router

    required = {
        "/phase13/status",
        "/phase13/drift",
        "/phase13/performance",
        "/phase13/retraining-proposal",
        "/phase13/governance-gate",
    }

    router_paths = {
        route.path
        for route in phase13_router.routes
        if hasattr(route, "path")
    }

    missing_from_router = sorted(required - router_paths)
    if missing_from_router:
        raise AssertionError(
            f"Missing Phase 13 router paths: {missing_from_router}"
        )

    # Verify the router is actually wired into the application source.
    app_path = PROJECT_ROOT / "src" / "api" / "app.py"
    app_text = app_path.read_text(encoding="utf-8")

    import_line = (
        "from api.phase13_routes import router as "
        "phase13_governance_router"
    )
    include_line = "app.include_router(phase13_governance_router)"

    if import_line not in app_text:
        raise AssertionError(
            "Phase 13 router import is missing from src/api/app.py"
        )
    if include_line not in app_text:
        raise AssertionError(
            "Phase 13 router is not included in src/api/app.py"
        )

    return sorted(required)


def main() -> None:
    summary = _certify_reports()
    routes = _certify_api()

    output = {
        "schema_version": "phase13_final_certification_v1",
        "status": "PASS",
        "summary": summary,
        "verified_api_routes": routes,
        "scientific_boundary": {
            "certified_phase10_model_read_only": True,
            "test_not_used_for_model_selection": True,
            "no_automatic_retraining": True,
            "no_automatic_recalibration": True,
            "no_automatic_promotion": True,
            "no_automatic_threshold_change": True,
            "human_approval_required": True,
        },
    }

    report_path = REPORT_DIR / "phase13_final_certification_v1_report.json"
    report_path.write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(output, indent=2))
    print("GRAPHSHIELD_PHASE13_CERTIFICATION=PASS")


if __name__ == "__main__":
    main()
