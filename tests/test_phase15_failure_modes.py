from pathlib import Path

from reliability.phase15_failure_modes import review_failure_modes


def test_failure_mode_review_passes_with_fail_closed_contracts(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/api").mkdir(parents=True)
    (tmp_path / "src/enterprise").mkdir(parents=True)
    (tmp_path / "infra/phase14/k8s").mkdir(parents=True)

    (tmp_path / "src/api/phase14_routes.py").write_text(
        "status_code=503",
        encoding="utf-8",
    )
    (tmp_path / "src/enterprise/phase14_runtime.py").write_text(
        "strict_readiness",
        encoding="utf-8",
    )
    (tmp_path / "src/enterprise/phase14_artifact_manifest.py").write_text(
        "sha256_mismatch",
        encoding="utf-8",
    )
    (tmp_path / "infra/phase14/k8s/deployment.yaml").write_text(
        "livenessProbe:\nstartupProbe:\nmaxUnavailable: 0\nmaxSurge: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "infra/phase14/k8s/pdb.yaml").write_text(
        "minAvailable: 1",
        encoding="utf-8",
    )

    report = review_failure_modes(
        project_root=tmp_path,
        output_path=tmp_path / "report.json",
    )
    assert report["status"] == "PASS"
    assert report["governance"]["no_chaos_action_against_live_system"] is True
