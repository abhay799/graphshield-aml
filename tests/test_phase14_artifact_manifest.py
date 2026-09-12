import json
from pathlib import Path

from enterprise.phase14_artifact_manifest import (
    build_artifact_manifest,
    verify_artifact_manifest,
)


def test_manifest_build_and_verify(tmp_path: Path) -> None:
    artifact = tmp_path / "models" / "model.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"certified-artifact")

    manifest_path = tmp_path / "manifest.json"

    report = build_artifact_manifest(
        project_root=tmp_path,
        artifact_paths=("models/model.bin",),
        output_path=manifest_path,
    )

    assert report["status"] == "PASS"
    assert report["artifacts"][0]["sha256"]

    verified = verify_artifact_manifest(
        manifest_path=manifest_path,
        project_root=tmp_path,
    )

    assert verified["verified"] is True
    assert verified["mismatches"] == []


def test_manifest_detects_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "models" / "model.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"original")

    manifest_path = tmp_path / "manifest.json"

    build_artifact_manifest(
        project_root=tmp_path,
        artifact_paths=("models/model.bin",),
        output_path=manifest_path,
    )

    artifact.write_bytes(b"changed")

    verified = verify_artifact_manifest(
        manifest_path=manifest_path,
        project_root=tmp_path,
    )

    assert verified["verified"] is False
    assert verified["status"] == "FAIL"
    reasons = {item["reason"] for item in verified["mismatches"]}
    assert "sha256_mismatch" in reasons or "size_mismatch" in reasons
