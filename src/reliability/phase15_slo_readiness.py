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
    / "slo_readiness_v1_report.json"
)

SLO_CONTRACT = {
    "availability_target": 0.995,
    "p95_latency_ms_target": 1000.0,
    "server_error_rate_target": 0.01,
}


def _contains(path: Path, *tokens: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return all(token in text for token in tokens)


def verify_slo_readiness(
    *,
    project_root: Path = PROJECT_ROOT,
    output_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    observability = project_root / "src" / "api" / "observability.py"
    phase14_routes = project_root / "src" / "api" / "phase14_routes.py"
    deployment = (
        project_root
        / "infra"
        / "phase14"
        / "k8s"
        / "deployment.yaml"
    )
    hpa = (
        project_root
        / "infra"
        / "phase14"
        / "k8s"
        / "hpa.yaml"
    )

    checks = {
        "request_count_metric_present": _contains(
            observability,
            "graphshield_http_requests_total",
        ),
        "request_latency_metric_present": _contains(
            observability,
            "graphshield_http_request_duration_seconds",
        ),
        "metrics_endpoint_present": _contains(
            observability,
            "@app.get('/metrics'",
        ),
        "liveness_endpoint_present": _contains(
            phase14_routes,
            '@router.get("/live"',
        ),
        "readiness_endpoint_present": _contains(
            phase14_routes,
            '@router.get("/ready"',
        ),
        "kubernetes_liveness_probe_present": _contains(
            deployment,
            "livenessProbe:",
            "path: /live",
        ),
        "kubernetes_readiness_probe_present": _contains(
            deployment,
            "readinessProbe:",
            "path: /ready",
        ),
        "horizontal_autoscaling_contract_present": _contains(
            hpa,
            "kind: HorizontalPodAutoscaler",
            "minReplicas:",
            "maxReplicas:",
        ),
    }

    ready = all(checks.values())

    report = {
        "schema_version": "phase15_slo_readiness_v1",
        "status": "PASS" if ready else "FAIL",
        "slo_contract": SLO_CONTRACT,
        "checks": checks,
        "interpretation": {
            "this_verifies_slo_observability_readiness_not_production_slo_attainment": True,
            "production_slo_attainment_requires_real_traffic_measurements": True,
        },
        "governance": {
            "no_synthetic_claim_of_production_availability": True,
            "no_synthetic_claim_of_production_latency": True,
            "no_automatic_scaling_policy_change": True,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = verify_slo_readiness()
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit("GRAPHSHIELD_PHASE15_SLO_READINESS=FAIL")
    print("GRAPHSHIELD_PHASE15_SLO_READINESS=PASS")


if __name__ == "__main__":
    main()
