from pathlib import Path


def test_phase14_container_is_non_root() -> None:
    text = Path("infra/phase14/Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "USER graphshield" in text
    assert "EXPOSE 8000" in text


def test_kubernetes_has_health_probes_and_security_context() -> None:
    text = Path(
        "infra/phase14/k8s/deployment.yaml"
    ).read_text(encoding="utf-8")

    assert "path: /ready" in text
    assert "path: /live" in text
    assert "runAsNonRoot: true" in text
    assert "allowPrivilegeEscalation: false" in text
    assert "readOnlyRootFilesystem: true" in text
    assert "drop:" in text
    assert "- ALL" in text


def test_certified_artifact_mounts_are_read_only() -> None:
    text = Path(
        "infra/phase14/k8s/deployment.yaml"
    ).read_text(encoding="utf-8")

    assert "mountPath: /app/models" in text
    assert "mountPath: /app/reports" in text
    assert text.count("readOnly: true") >= 4
