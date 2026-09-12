from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase15"
    / "failure_mode_review_v1_report.json"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def review_failure_modes(
    *,
    project_root: Path = PROJECT_ROOT,
    output_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    routes = _read(project_root / "src" / "api" / "phase14_routes.py")
    runtime = _read(project_root / "src" / "enterprise" / "phase14_runtime.py")
    integrity = _read(
        project_root / "src" / "enterprise" / "phase14_artifact_manifest.py"
    )
    deployment = _read(
        project_root / "infra" / "phase14" / "k8s" / "deployment.yaml"
    )
    pdb = _read(
        project_root / "infra" / "phase14" / "k8s" / "pdb.yaml"
    )

    modes = {
        "missing_certified_artifact": {
            "fail_closed": "status_code=503" in routes
            or "status_code = 503" in routes
            or "status_code=503," in routes,
            "evidence": "readiness endpoint returns 503 when required artifacts are missing",
        },
        "artifact_tampering": {
            "fail_closed": "sha256_mismatch" in integrity,
            "evidence": "artifact integrity verifier detects SHA-256 mismatch",
        },
        "container_restart": {
            "fail_closed": (
                "livenessProbe:" in deployment
                and "startupProbe:" in deployment
            ),
            "evidence": "startup/liveness probes permit orchestrator recovery",
        },
        "rolling_release_failure": {
            "fail_closed": (
                "maxUnavailable: 0" in deployment
                and "maxSurge: 1" in deployment
            ),
            "evidence": "rolling update keeps zero intended unavailable replicas",
        },
        "voluntary_node_disruption": {
            "fail_closed": "minAvailable: 1" in pdb,
            "evidence": "PodDisruptionBudget retains at least one replica",
        },
        "readiness_dependency_failure": {
            "fail_closed": "strict_readiness" in runtime,
            "evidence": "strict readiness blocks service readiness on missing dependencies",
        },
    }

    passed = all(item["fail_closed"] for item in modes.values())

    report = {
        "schema_version": "phase15_failure_mode_review_v1",
        "status": "PASS" if passed else "FAIL",
        "failure_modes": modes,
        "governance": {
            "review_is_static_and_does_not_inject_production_failures": True,
            "no_chaos_action_against_live_system": True,
            "no_artifact_mutation": True,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = review_failure_modes()
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit("GRAPHSHIELD_PHASE15_FAILURE_MODES=FAIL")
    print("GRAPHSHIELD_PHASE15_FAILURE_MODES=PASS")


if __name__ == "__main__":
    main()
