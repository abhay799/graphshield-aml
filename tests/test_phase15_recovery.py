from pathlib import Path

from enterprise.phase14_artifact_manifest import build_artifact_manifest
from reliability.phase15_recovery_verifier import verify_recovery_readiness


def test_recovery_readiness_requires_integrity_and_rollback_contract(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "models/model.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"frozen")

    manifest = tmp_path / "manifest.json"
    build_artifact_manifest(
        project_root=tmp_path,
        artifact_paths=("models/model.bin",),
        output_path=manifest,
    )

    deploy = tmp_path / "infra/phase14/k8s/deployment.yaml"
    deploy.parent.mkdir(parents=True)
    deploy.write_text(
        "revisionHistoryLimit: 5\n"
        "maxUnavailable: 0\n"
        "maxSurge: 1\n"
        "mountPath: /app/models\n"
        "readOnly: true\n",
        encoding="utf-8",
    )

    report = verify_recovery_readiness(
        project_root=tmp_path,
        manifest_path=manifest,
        output_path=tmp_path / "recovery.json",
    )

    assert report["status"] == "PASS"
    assert report["rollback_contract"][
        "rollback_does_not_modify_certified_artifacts"
    ] is True
