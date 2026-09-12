from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = PROJECT_ROOT / "reports" / "v2" / "phase14"

REPORTS = {
    "artifact_manifest": (
        REPORT_DIR / "artifact_manifest_v1.json"
    ),
    "deployment_gate": (
        REPORT_DIR / "deployment_gate_v1_report.json"
    ),
    "release_readiness": (
        REPORT_DIR / "release_readiness_v1_report.json"
    ),
}

REQUIRED_PHASE14_ROUTES = {
    "/live",
    "/ready",
    "/deployment",
    "/deployment/integrity",
}


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssertionError(
            f"Missing required Phase 14 report: {path}"
        )
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def _require_true(
    mapping: dict[str, Any],
    key: str,
    description: str,
) -> None:
    if mapping.get(key) is not True:
        raise AssertionError(
            f"Expected {description}=true, "
            f"got {mapping.get(key)!r}"
        )


def _require_false(
    mapping: dict[str, Any],
    key: str,
    description: str,
) -> None:
    if mapping.get(key) is not False:
        raise AssertionError(
            f"Expected {description}=false, "
            f"got {mapping.get(key)!r}"
        )


def _certify_reports() -> dict[str, Any]:
    manifest = _read(REPORTS["artifact_manifest"])
    gate = _read(REPORTS["deployment_gate"])
    release = _read(REPORTS["release_readiness"])

    if manifest.get("status") != "PASS":
        raise AssertionError(
            "Artifact manifest must pass."
        )
    if manifest.get("missing_artifacts"):
        raise AssertionError(
            "Certified artifact manifest has missing artifacts."
        )

    manifest_gov = manifest.get("governance", {})
    _require_true(
        manifest_gov,
        "certified_artifacts_read_only",
        "certified_artifacts_read_only",
    )
    _require_false(
        manifest_gov,
        "manifest_generation_modifies_artifacts",
        "manifest_generation_modifies_artifacts",
    )
    _require_false(
        manifest_gov,
        "automatic_model_replacement",
        "automatic_model_replacement",
    )
    _require_false(
        manifest_gov,
        "automatic_model_promotion",
        "automatic_model_promotion",
    )

    if gate.get("status") != "PASS":
        raise AssertionError(
            "Phase 14 deployment gate must pass."
        )
    _require_true(
        gate,
        "deployment_allowed",
        "deployment_allowed",
    )

    gate_checks = gate.get("checks", {})
    for key in (
        "phase13_certification_pass",
        "runtime_readiness_pass",
        "artifact_integrity_pass",
    ):
        _require_true(
            gate_checks,
            key,
            key,
        )

    gate_gov = gate.get("governance", {})
    _require_false(
        gate_gov,
        "automatic_deployment",
        "automatic_deployment",
    )
    _require_false(
        gate_gov,
        "automatic_model_promotion",
        "automatic_model_promotion",
    )
    _require_false(
        gate_gov,
        "automatic_artifact_replacement",
        "automatic_artifact_replacement",
    )
    _require_true(
        gate_gov,
        "human_release_approval_required",
        "human_release_approval_required",
    )

    if release.get("status") != "PASS":
        raise AssertionError(
            "Release readiness must pass."
        )
    _require_true(
        release,
        "release_ready_for_human_approval",
        "release_ready_for_human_approval",
    )

    release_gov = release.get(
        "release_governance",
        {},
    )
    _require_false(
        release_gov,
        "automatic_production_release",
        "automatic_production_release",
    )
    _require_true(
        release_gov,
        "human_release_approval_required",
        "human_release_approval_required",
    )
    _require_false(
        release_gov,
        "automatic_model_promotion",
        "automatic_model_promotion",
    )
    _require_false(
        release_gov,
        "automatic_threshold_change",
        "automatic_threshold_change",
    )
    _require_false(
        release_gov,
        "automatic_retraining",
        "automatic_retraining",
    )
    _require_false(
        release_gov,
        "automatic_regulatory_action",
        "automatic_regulatory_action",
    )

    rollback = release.get(
        "rollback_contract",
        {},
    )
    for key in (
        "rollback_is_manual_or_orchestrator_controlled",
        "rollback_requires_previous_known_good_release",
        "certified_model_artifacts_are_not_mutated_by_rollback",
        "database_or_case_state_is_not_rewritten_by_release_gate",
    ):
        _require_true(
            rollback,
            key,
            key,
        )

    return {
        "artifact_manifest_status": manifest.get(
            "status"
        ),
        "artifact_count": manifest.get(
            "artifact_count"
        ),
        "deployment_gate_status": gate.get(
            "status"
        ),
        "release_readiness_status": release.get(
            "status"
        ),
    }


def _certify_api() -> list[str]:
    from api.phase14_routes import (
        router as phase14_router,
    )

    router_paths = {
        route.path
        for route in phase14_router.routes
        if hasattr(route, "path")
    }

    missing = sorted(
        REQUIRED_PHASE14_ROUTES - router_paths
    )
    if missing:
        raise AssertionError(
            f"Missing Phase 14 routes: {missing}"
        )

    app_path = (
        PROJECT_ROOT
        / "src"
        / "api"
        / "app.py"
    )
    app_text = app_path.read_text(
        encoding="utf-8"
    )

    if (
        "app.include_router(phase14_enterprise_router)"
        not in app_text
    ):
        raise AssertionError(
            "Phase 14 router is not wired into app.py"
        )

    if "install_enterprise_security(app)" not in app_text:
        raise AssertionError(
            "Phase 14 enterprise security is not installed."
        )

    return sorted(REQUIRED_PHASE14_ROUTES)


def _certify_infra() -> dict[str, bool]:
    k8s_dir = (
        PROJECT_ROOT
        / "infra"
        / "phase14"
        / "k8s"
    )

    required_files = (
        "namespace.yaml",
        "configmap.yaml",
        "pvc.yaml",
        "deployment.yaml",
        "service.yaml",
        "networkpolicy.yaml",
        "serviceaccount.yaml",
        "pdb.yaml",
        "hpa.yaml",
    )

    missing = [
        name
        for name in required_files
        if not (k8s_dir / name).exists()
    ]

    if missing:
        raise AssertionError(
            f"Missing Phase 14 Kubernetes files: {missing}"
        )

    dockerfile = (
        PROJECT_ROOT
        / "infra"
        / "phase14"
        / "Dockerfile"
    )

    docker_text = dockerfile.read_text(
        encoding="utf-8"
    )
    if "USER graphshield" not in docker_text:
        raise AssertionError(
            "Phase 14 container must run non-root."
        )

    deploy_text = (
        k8s_dir / "deployment.yaml"
    ).read_text(encoding="utf-8")

    required_tokens = (
        "runAsNonRoot: true",
        "readOnlyRootFilesystem: true",
        "allowPrivilegeEscalation: false",
        "path: /live",
        "path: /ready",
        "maxUnavailable: 0",
        "startupProbe:",
        "seccompProfile:",
    )

    for token in required_tokens:
        if token not in deploy_text:
            raise AssertionError(
                f"Deployment missing required contract: {token}"
            )

    return {
        "docker_non_root": True,
        "kubernetes_contract_complete": True,
    }


def main() -> None:
    summary = _certify_reports()
    routes = _certify_api()
    infra = _certify_infra()

    result = {
        "schema_version": (
            "phase14_final_certification_v1"
        ),
        "status": "PASS",
        "summary": summary,
        "verified_api_routes": routes,
        "infrastructure": infra,
        "enterprise_boundary": {
            "certified_models_read_only": True,
            "human_release_approval_required": True,
            "automatic_model_promotion": False,
            "automatic_retraining": False,
            "automatic_threshold_change": False,
            "automatic_regulatory_action": False,
        },
    }

    output_path = (
        REPORT_DIR
        / "phase14_final_certification_v1_report.json"
    )
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2))
    print(
        "GRAPHSHIELD_PHASE14_CERTIFICATION=PASS"
    )


if __name__ == "__main__":
    main()
