from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from enterprise.phase14_artifact_manifest import (
    MANIFEST_PATH,
    verify_artifact_manifest,
)
from enterprise.phase14_runtime import PROJECT_ROOT

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase15"
    / "recovery_readiness_v1_report.json"
)


def verify_recovery_readiness(
    *,
    project_root: Path = PROJECT_ROOT,
    manifest_path: Path = MANIFEST_PATH,
    output_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    integrity = verify_artifact_manifest(
        manifest_path=manifest_path,
        project_root=project_root,
    )

    deployment_path = (
        project_root
        / "infra"
        / "phase14"
        / "k8s"
        / "deployment.yaml"
    )
    deployment = (
        deployment_path.read_text(encoding="utf-8")
        if deployment_path.exists()
        else ""
    )

    checks = {
        "certified_artifact_integrity_verified": bool(
            integrity.get("verified")
        ),
        "rolling_update_contract_present": (
            "maxUnavailable: 0" in deployment
            and "maxSurge: 1" in deployment
        ),
        "artifact_mounts_read_only": (
            "mountPath: /app/models" in deployment
            and "readOnly: true" in deployment
        ),
        "revision_history_retained": "revisionHistoryLimit:" in deployment,
    }

    passed = all(checks.values())

    report = {
        "schema_version": "phase15_recovery_readiness_v1",
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "rollback_contract": {
            "rollback_target_must_be_previous_known_good_release": True,
            "rollback_does_not_retrain_models": True,
            "rollback_does_not_recalibrate_models": True,
            "rollback_does_not_modify_certified_artifacts": True,
            "rollback_execution_is_not_automatic_from_this_verifier": True,
        },
        "artifact_integrity": {
            "verified": integrity.get("verified", False),
            "mismatch_count": len(integrity.get("mismatches", [])),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = verify_recovery_readiness()
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit("GRAPHSHIELD_PHASE15_RECOVERY_READINESS=FAIL")
    print("GRAPHSHIELD_PHASE15_RECOVERY_READINESS=PASS")


if __name__ == "__main__":
    main()
