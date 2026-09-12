import json
from pathlib import Path

from enterprise.phase14_artifact_manifest import (
    build_artifact_manifest,
)
from enterprise.phase14_release_readiness import (
    build_release_readiness,
)


def _write(
    path: Path,
    payload: dict,
) -> None:
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_release_readiness_passes_with_gate_and_integrity(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"frozen")

    manifest = tmp_path / "manifest.json"
    build_artifact_manifest(
        project_root=tmp_path,
        artifact_paths=("model.bin",),
        output_path=manifest,
    )

    gate = tmp_path / "gate.json"
    _write(
        gate,
        {
            "status": "PASS",
            "deployment_allowed": True,
        },
    )

    report = build_release_readiness(
        deployment_gate_path=gate,
        manifest_path=manifest,
        project_root=tmp_path,
        output_path=tmp_path / "release.json",
    )

    assert report["status"] == "PASS"
    assert (
        report["release_ready_for_human_approval"]
        is True
    )
    assert (
        report["release_governance"][
            "automatic_production_release"
        ]
        is False
    )


def test_release_readiness_blocks_failed_gate(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"frozen")

    manifest = tmp_path / "manifest.json"
    build_artifact_manifest(
        project_root=tmp_path,
        artifact_paths=("model.bin",),
        output_path=manifest,
    )

    gate = tmp_path / "gate.json"
    _write(
        gate,
        {
            "status": "BLOCKED",
            "deployment_allowed": False,
        },
    )

    report = build_release_readiness(
        deployment_gate_path=gate,
        manifest_path=manifest,
        project_root=tmp_path,
        output_path=tmp_path / "release.json",
    )

    assert report["status"] == "BLOCKED"
    assert (
        report["release_ready_for_human_approval"]
        is False
    )
