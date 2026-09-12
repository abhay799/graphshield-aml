import json
from pathlib import Path

import enterprise.phase14_deployment_gate as gate
from enterprise.phase14_artifact_manifest import build_artifact_manifest
from enterprise.phase14_runtime import Phase14RuntimeConfig


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_deployment_gate_passes_only_with_certification_and_integrity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"frozen")

    manifest = tmp_path / "manifest.json"
    build_artifact_manifest(
        project_root=tmp_path,
        artifact_paths=("model.bin",),
        output_path=manifest,
    )

    phase13 = tmp_path / "phase13.json"
    _write(phase13, {"status": "PASS"})

    monkeypatch.setattr(
        gate,
        "get_runtime_config",
        lambda: Phase14RuntimeConfig(
            environment="test",
            release="phase14",
            commit_sha="abc",
            region="test",
            instance_id="pod",
            strict_readiness=True,
            enable_hsts=False,
            required_paths=("model.bin",),
        ),
    )

    report = gate.run_deployment_gate(
        project_root=tmp_path,
        phase13_certification_path=phase13,
        manifest_path=manifest,
        output_path=tmp_path / "gate.json",
    )

    assert report["status"] == "PASS"
    assert report["deployment_allowed"] is True
    assert report["governance"]["automatic_deployment"] is False


def test_deployment_gate_blocks_tampered_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"frozen")

    manifest = tmp_path / "manifest.json"
    build_artifact_manifest(
        project_root=tmp_path,
        artifact_paths=("model.bin",),
        output_path=manifest,
    )

    artifact.write_bytes(b"tampered")

    phase13 = tmp_path / "phase13.json"
    _write(phase13, {"status": "PASS"})

    monkeypatch.setattr(
        gate,
        "get_runtime_config",
        lambda: Phase14RuntimeConfig(
            environment="test",
            release="phase14",
            commit_sha="abc",
            region="test",
            instance_id="pod",
            strict_readiness=True,
            enable_hsts=False,
            required_paths=("model.bin",),
        ),
    )

    report = gate.run_deployment_gate(
        project_root=tmp_path,
        phase13_certification_path=phase13,
        manifest_path=manifest,
        output_path=tmp_path / "gate.json",
    )

    assert report["status"] == "BLOCKED"
    assert report["deployment_allowed"] is False
