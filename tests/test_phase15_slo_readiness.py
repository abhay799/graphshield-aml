from pathlib import Path

from reliability.phase15_slo_readiness import verify_slo_readiness


def test_slo_readiness_requires_observability_and_probes(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/api").mkdir(parents=True)
    (tmp_path / "infra/phase14/k8s").mkdir(parents=True)

    (tmp_path / "src/api/observability.py").write_text(
        "graphshield_http_requests_total\n"
        "graphshield_http_request_duration_seconds\n"
        "@app.get('/metrics'\n",
        encoding="utf-8",
    )
    (tmp_path / "src/api/phase14_routes.py").write_text(
        '@router.get("/live"\n@router.get("/ready"\n',
        encoding="utf-8",
    )
    (tmp_path / "infra/phase14/k8s/deployment.yaml").write_text(
        "livenessProbe:\n path: /live\n"
        "readinessProbe:\n path: /ready\n",
        encoding="utf-8",
    )
    (tmp_path / "infra/phase14/k8s/hpa.yaml").write_text(
        "kind: HorizontalPodAutoscaler\nminReplicas: 2\nmaxReplicas: 6\n",
        encoding="utf-8",
    )

    report = verify_slo_readiness(
        project_root=tmp_path,
        output_path=tmp_path / "report.json",
    )
    assert report["status"] == "PASS"
    assert report["interpretation"][
        "production_slo_attainment_requires_real_traffic_measurements"
    ] is True
