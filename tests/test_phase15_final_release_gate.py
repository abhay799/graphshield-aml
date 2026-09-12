import json
from pathlib import Path

from reliability.phase15_final_release_gate import (
    build_final_release_gate,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _phase15_reports(tmp_path: Path) -> dict[str, Path]:
    slo = tmp_path / "slo.json"
    failure = tmp_path / "failure.json"
    recovery = tmp_path / "recovery.json"
    smoke = tmp_path / "smoke.json"

    _write(
        slo,
        {
            "status": "PASS",
            "interpretation": {
                "this_verifies_slo_observability_readiness_not_production_slo_attainment": True,
                "production_slo_attainment_requires_real_traffic_measurements": True,
            },
        },
    )
    _write(
        failure,
        {
            "status": "PASS",
            "governance": {
                "review_is_static_and_does_not_inject_production_failures": True,
                "no_chaos_action_against_live_system": True,
            },
        },
    )
    _write(
        recovery,
        {
            "status": "PASS",
            "rollback_contract": {
                "rollback_does_not_retrain_models": True,
                "rollback_does_not_recalibrate_models": True,
                "rollback_does_not_modify_certified_artifacts": True,
                "rollback_execution_is_not_automatic_from_this_verifier": True,
            },
        },
    )
    _write(
        smoke,
        {
            "status": "PASS",
            "interpretation": {
                "smoke_is_in_process_not_external_production_traffic": True,
                "smoke_does_not_prove_end_to_end_cloud_networking": True,
            },
            "governance": {
                "read_only_smoke_checks_only": True,
                "no_case_mutation": True,
                "no_model_mutation": True,
            },
        },
    )

    return {
        "slo_readiness": slo,
        "failure_modes": failure,
        "recovery_readiness": recovery,
        "production_smoke": smoke,
    }


def test_final_release_gate_passes_only_for_human_approval(
    tmp_path: Path,
) -> None:
    phase14 = tmp_path / "phase14.json"
    _write(phase14, {"status": "PASS"})

    report = build_final_release_gate(
        phase14_certification_path=phase14,
        report_paths=_phase15_reports(tmp_path),
        output_path=tmp_path / "gate.json",
    )

    assert report["status"] == "PASS"
    assert report["final_release_ready_for_human_approval"] is True
    assert report["release_governance"][
        "automatic_production_release"
    ] is False
    assert report["scientific_boundary"][
        "production_slo_attainment_claimed"
    ] is False


def test_final_release_gate_blocks_failed_dependency(
    tmp_path: Path,
) -> None:
    phase14 = tmp_path / "phase14.json"
    _write(phase14, {"status": "FAIL"})

    report = build_final_release_gate(
        phase14_certification_path=phase14,
        report_paths=_phase15_reports(tmp_path),
        output_path=tmp_path / "gate.json",
    )

    assert report["status"] == "BLOCKED"
    assert report["final_release_ready_for_human_approval"] is False
