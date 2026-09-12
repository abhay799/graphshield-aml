from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHASE15_DIR = PROJECT_ROOT / "reports" / "v2" / "phase15"

REPORTS = {
    "slo_readiness": PHASE15_DIR / "slo_readiness_v1_report.json",
    "failure_modes": PHASE15_DIR / "failure_mode_review_v1_report.json",
    "recovery_readiness": PHASE15_DIR / "recovery_readiness_v1_report.json",
    "production_smoke": PHASE15_DIR / "production_smoke_v1_report.json",
    "final_release_gate": PHASE15_DIR / "final_release_gate_v1_report.json",
}

PHASE_CERTIFICATIONS = {
    "phase10": (
        PROJECT_ROOT
        / "reports"
        / "v2"
        / "phase10"
        / "phase10_certification_v1.json"
    ),
    "phase11": (
        PROJECT_ROOT
        / "reports"
        / "v2"
        / "phase11"
        / "phase11_certification_v1.json"
    ),
    "phase12": (
        PROJECT_ROOT
        / "reports"
        / "v2"
        / "phase12"
        / "phase12_certification_v1.json"
    ),
    "phase13": (
        PROJECT_ROOT
        / "reports"
        / "v2"
        / "phase13"
        / "phase13_final_certification_v1_report.json"
    ),
    "phase14": (
        PROJECT_ROOT
        / "reports"
        / "v2"
        / "phase14"
        / "phase14_final_certification_v1_report.json"
    ),
}

OUTPUT_PATH = PHASE15_DIR / "phase15_final_certification_v1_report.json"


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssertionError(f"Missing certification artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _require_true(mapping: dict[str, Any], key: str) -> None:
    if mapping.get(key) is not True:
        raise AssertionError(
            f"Expected {key}=true, got {mapping.get(key)!r}"
        )


def _require_false(mapping: dict[str, Any], key: str) -> None:
    if mapping.get(key) is not False:
        raise AssertionError(
            f"Expected {key}=false, got {mapping.get(key)!r}"
        )


def _certify_phase15_reports() -> dict[str, Any]:
    reports = {
        name: _read(path)
        for name, path in REPORTS.items()
    }

    for name, report in reports.items():
        if report.get("status") != "PASS":
            raise AssertionError(
                f"{name} must be PASS, got {report.get('status')!r}"
            )

    gate = reports["final_release_gate"]

    _require_true(
        gate,
        "final_release_ready_for_human_approval",
    )

    release_gov = gate.get("release_governance", {})
    _require_false(
        release_gov,
        "automatic_production_release",
    )
    _require_true(
        release_gov,
        "human_release_approval_required",
    )
    for key in (
        "automatic_model_promotion",
        "automatic_retraining",
        "automatic_recalibration",
        "automatic_threshold_change",
        "automatic_regulatory_submission",
        "automatic_account_blocking",
        "automatic_case_closure",
    ):
        _require_false(release_gov, key)

    scientific = gate.get("scientific_boundary", {})
    _require_false(
        scientific,
        "production_slo_attainment_claimed",
    )
    _require_false(
        scientific,
        "external_cloud_smoke_claimed",
    )
    _require_true(
        scientific,
        "real_traffic_required_for_production_slo_claims",
    )

    recovery = reports["recovery_readiness"]
    rollback = recovery.get("rollback_contract", {})
    for key in (
        "rollback_target_must_be_previous_known_good_release",
        "rollback_does_not_retrain_models",
        "rollback_does_not_recalibrate_models",
        "rollback_does_not_modify_certified_artifacts",
        "rollback_execution_is_not_automatic_from_this_verifier",
    ):
        _require_true(rollback, key)

    return {
        "slo_readiness": reports["slo_readiness"]["status"],
        "failure_modes": reports["failure_modes"]["status"],
        "recovery_readiness": reports["recovery_readiness"]["status"],
        "production_smoke": reports["production_smoke"]["status"],
        "final_release_gate": gate["status"],
    }


def _certify_prior_phases() -> dict[str, str]:
    statuses: dict[str, str] = {}

    for phase, path in PHASE_CERTIFICATIONS.items():
        report = _read(path)
        status = str(report.get("status", "")).upper()

        # Earlier certification artifacts may use certification/status-like
        # fields, but all current certified reports expose PASS as status.
        if status != "PASS":
            # Preserve compatibility with older phase report naming.
            alternate = str(
                report.get("certification", report.get("result", ""))
            ).upper()
            if alternate != "PASS":
                raise AssertionError(
                    f"{phase} certification is not PASS: {path}"
                )
            status = "PASS"

        statuses[phase] = status

    return statuses


def _certify_phase15_modules() -> list[str]:
    required = (
        "src/reliability/phase15_slo_readiness.py",
        "src/reliability/phase15_failure_modes.py",
        "src/reliability/phase15_recovery_verifier.py",
        "src/reliability/phase15_smoke.py",
        "src/reliability/phase15_final_release_gate.py",
    )

    missing = [
        rel
        for rel in required
        if not (PROJECT_ROOT / rel).exists()
    ]

    if missing:
        raise AssertionError(
            f"Missing Phase 15 modules: {missing}"
        )

    return list(required)


def main() -> None:
    phase15 = _certify_phase15_reports()
    prior = _certify_prior_phases()
    modules = _certify_phase15_modules()

    result = {
        "schema_version": "phase15_final_certification_v1",
        "status": "PASS",
        "project": "GraphShield AML",
        "certified_through_phase": 15,
        "phase15": phase15,
        "prior_phase_certifications": prior,
        "verified_phase15_modules": modules,
        "final_boundary": {
            "decision_support_only": True,
            "human_review_required": True,
            "human_release_approval_required": True,
            "certified_models_read_only": True,
            "automatic_retraining": False,
            "automatic_model_promotion": False,
            "automatic_recalibration": False,
            "automatic_threshold_change": False,
            "automatic_account_blocking": False,
            "automatic_case_closure": False,
            "automatic_sar_str_filing": False,
            "automatic_regulatory_submission": False,
            "production_slo_attainment_claimed": False,
            "external_cloud_smoke_claimed": False,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2))
    print("GRAPHSHIELD_PHASE15_CERTIFICATION=PASS")


if __name__ == "__main__":
    main()
