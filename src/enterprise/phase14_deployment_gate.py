from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from enterprise.phase14_artifact_manifest import (
    MANIFEST_PATH,
    verify_artifact_manifest,
)
from enterprise.phase14_runtime import (
    PROJECT_ROOT,
    evaluate_readiness,
    get_runtime_config,
)

PHASE13_CERTIFICATION = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "phase13_final_certification_v1_report.json"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase14"
    / "deployment_gate_v1_report.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def run_deployment_gate(
    *,
    project_root: Path = PROJECT_ROOT,
    phase13_certification_path: Path = PHASE13_CERTIFICATION,
    manifest_path: Path = MANIFEST_PATH,
    output_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    runtime = get_runtime_config()
    readiness = evaluate_readiness(
        runtime,
        project_root=project_root,
    )

    try:
        phase13 = _read_json(phase13_certification_path)
        phase13_pass = phase13.get("status") == "PASS"
    except FileNotFoundError:
        phase13_pass = False

    integrity = verify_artifact_manifest(
        manifest_path=manifest_path,
        project_root=project_root,
    )

    checks = {
        "phase13_certification_pass": phase13_pass,
        "runtime_readiness_pass": bool(readiness["ready"]),
        "artifact_integrity_pass": bool(integrity["verified"]),
    }

    allowed = all(checks.values())

    report = {
        "schema_version": "phase14_deployment_gate_v1",
        "status": "PASS" if allowed else "BLOCKED",
        "deployment_allowed": allowed,
        "checks": checks,
        "runtime": runtime.public_metadata(),
        "integrity": {
            "verified": integrity["verified"],
            "mismatch_count": len(integrity["mismatches"]),
        },
        "governance": {
            "gate_is_pre_deployment_only": True,
            "automatic_deployment": False,
            "automatic_model_promotion": False,
            "automatic_artifact_replacement": False,
            "human_release_approval_required": True,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = run_deployment_gate()
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(
            "GRAPHSHIELD_PHASE14_DEPLOYMENT_GATE=BLOCKED"
        )
    print("GRAPHSHIELD_PHASE14_DEPLOYMENT_GATE=PASS")


if __name__ == "__main__":
    main()
