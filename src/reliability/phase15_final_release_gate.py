from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHASE15_DIR = PROJECT_ROOT / "reports" / "v2" / "phase15"

REPORT_PATH = PHASE15_DIR / "final_release_gate_v1_report.json"

PHASE14_CERTIFICATION = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase14"
    / "phase14_final_certification_v1_report.json"
)

REQUIRED_PHASE15_REPORTS = {
    "slo_readiness": PHASE15_DIR / "slo_readiness_v1_report.json",
    "failure_modes": PHASE15_DIR / "failure_mode_review_v1_report.json",
    "recovery_readiness": PHASE15_DIR / "recovery_readiness_v1_report.json",
    "production_smoke": PHASE15_DIR / "production_smoke_v1_report.json",
}


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def build_final_release_gate(
    *,
    phase14_certification_path: Path = PHASE14_CERTIFICATION,
    report_paths: dict[str, Path] = REQUIRED_PHASE15_REPORTS,
    output_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    try:
        phase14 = _read(phase14_certification_path)
        checks["phase14_certification_pass"] = (
            phase14.get("status") == "PASS"
        )
        details["phase14_certification"] = phase14.get("status")
    except FileNotFoundError:
        checks["phase14_certification_pass"] = False
        details["phase14_certification"] = "MISSING"

    loaded: dict[str, dict[str, Any]] = {}

    for name, path in report_paths.items():
        try:
            report = _read(path)
            loaded[name] = report
            checks[f"{name}_pass"] = report.get("status") == "PASS"
        except FileNotFoundError:
            checks[f"{name}_pass"] = False
            loaded[name] = {"status": "MISSING"}

    slo = loaded["slo_readiness"]
    failure = loaded["failure_modes"]
    recovery = loaded["recovery_readiness"]
    smoke = loaded["production_smoke"]

    slo_interpretation = slo.get("interpretation", {})
    smoke_interpretation = smoke.get("interpretation", {})
    smoke_governance = smoke.get("governance", {})
    failure_governance = failure.get("governance", {})
    rollback = recovery.get("rollback_contract", {})

    checks["slo_claim_boundary_preserved"] = (
        slo_interpretation.get(
            "this_verifies_slo_observability_readiness_not_production_slo_attainment"
        )
        is True
        and slo_interpretation.get(
            "production_slo_attainment_requires_real_traffic_measurements"
        )
        is True
    )

    checks["smoke_claim_boundary_preserved"] = (
        smoke_interpretation.get(
            "smoke_is_in_process_not_external_production_traffic"
        )
        is True
        and smoke_interpretation.get(
            "smoke_does_not_prove_end_to_end_cloud_networking"
        )
        is True
    )

    checks["smoke_is_read_only"] = (
        smoke_governance.get("read_only_smoke_checks_only") is True
        and smoke_governance.get("no_case_mutation") is True
        and smoke_governance.get("no_model_mutation") is True
    )

    checks["no_live_chaos_injection"] = (
        failure_governance.get(
            "review_is_static_and_does_not_inject_production_failures"
        )
        is True
        and failure_governance.get(
            "no_chaos_action_against_live_system"
        )
        is True
    )

    checks["rollback_preserves_certified_models"] = (
        rollback.get("rollback_does_not_retrain_models") is True
        and rollback.get("rollback_does_not_recalibrate_models") is True
        and rollback.get(
            "rollback_does_not_modify_certified_artifacts"
        )
        is True
        and rollback.get(
            "rollback_execution_is_not_automatic_from_this_verifier"
        )
        is True
    )

    passed = all(checks.values())

    report = {
        "schema_version": "phase15_final_release_gate_v1",
        "status": "PASS" if passed else "BLOCKED",
        "final_release_ready_for_human_approval": passed,
        "checks": checks,
        "details": details,
        "release_governance": {
            "automatic_production_release": False,
            "human_release_approval_required": True,
            "automatic_model_promotion": False,
            "automatic_retraining": False,
            "automatic_recalibration": False,
            "automatic_threshold_change": False,
            "automatic_regulatory_submission": False,
            "automatic_account_blocking": False,
            "automatic_case_closure": False,
        },
        "scientific_boundary": {
            "production_slo_attainment_claimed": False,
            "external_cloud_smoke_claimed": False,
            "real_traffic_required_for_production_slo_claims": True,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = build_final_release_gate()
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit("GRAPHSHIELD_PHASE15_FINAL_RELEASE_GATE=BLOCKED")
    print("GRAPHSHIELD_PHASE15_FINAL_RELEASE_GATE=PASS")


if __name__ == "__main__":
    main()
