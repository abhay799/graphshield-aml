from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from enterprise.phase14_artifact_manifest import (
    MANIFEST_PATH,
    verify_artifact_manifest,
)
from enterprise.phase14_deployment_gate import (
    REPORT_PATH as DEPLOYMENT_GATE_REPORT,
)
from enterprise.phase14_runtime import PROJECT_ROOT

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase14"
    / "release_readiness_v1_report.json"
)

SLO_TARGETS = {
    "availability_target": 0.995,
    "p95_latency_ms_target": 1000.0,
    "server_error_rate_target": 0.01,
}

ROLLBACK_CONTRACT = {
    "rollback_is_manual_or_orchestrator_controlled": True,
    "rollback_requires_previous_known_good_release": True,
    "certified_model_artifacts_are_not_mutated_by_rollback": True,
    "database_or_case_state_is_not_rewritten_by_release_gate": True,
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def build_release_readiness(
    *,
    deployment_gate_path: Path = DEPLOYMENT_GATE_REPORT,
    manifest_path: Path = MANIFEST_PATH,
    project_root: Path = PROJECT_ROOT,
    output_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    try:
        gate = _read_json(deployment_gate_path)
    except FileNotFoundError:
        gate = {
            "status": "MISSING",
            "deployment_allowed": False,
        }

    integrity = verify_artifact_manifest(
        manifest_path=manifest_path,
        project_root=project_root,
    )

    checks = {
        "deployment_gate_pass": (
            gate.get("status") == "PASS"
            and gate.get("deployment_allowed") is True
        ),
        "artifact_integrity_pass": (
            integrity.get("verified") is True
        ),
        "slo_contract_defined": True,
        "rollback_contract_defined": True,
    }

    ready = all(checks.values())

    report = {
        "schema_version": "phase14_release_readiness_v1",
        "status": "PASS" if ready else "BLOCKED",
        "release_ready_for_human_approval": ready,
        "checks": checks,
        "slo_targets": SLO_TARGETS,
        "rollback_contract": ROLLBACK_CONTRACT,
        "release_governance": {
            "automatic_production_release": False,
            "human_release_approval_required": True,
            "automatic_model_promotion": False,
            "automatic_threshold_change": False,
            "automatic_retraining": False,
            "automatic_regulatory_action": False,
        },
        "recommended_action": (
            "human_release_approval"
            if ready
            else "resolve_release_blockers"
        ),
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = build_release_readiness()
    print(json.dumps(report, indent=2))

    if report["status"] != "PASS":
        raise SystemExit(
            "GRAPHSHIELD_PHASE14_RELEASE_READINESS=BLOCKED"
        )

    print("GRAPHSHIELD_PHASE14_RELEASE_READINESS=PASS")


if __name__ == "__main__":
    main()
