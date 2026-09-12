from pathlib import Path

from enterprise.phase14_runtime import (
    Phase14RuntimeConfig,
    evaluate_readiness,
)


def _config(
    *,
    strict: bool,
    paths: tuple[str, ...],
) -> Phase14RuntimeConfig:
    return Phase14RuntimeConfig(
        environment="test",
        release="phase14-test",
        commit_sha="abc123",
        region="test-region",
        instance_id="test-instance",
        strict_readiness=strict,
        enable_hsts=False,
        required_paths=paths,
    )


def test_strict_readiness_fails_when_required_artifact_missing(
    tmp_path: Path,
) -> None:
    result = evaluate_readiness(
        _config(
            strict=True,
            paths=("models/frozen.joblib",),
        ),
        project_root=tmp_path,
    )
    assert result["ready"] is False
    assert result["status"] == "not_ready"
    assert result["missing_required_paths"] == [
        "models/frozen.joblib"
    ]


def test_strict_readiness_passes_when_artifacts_exist(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "models" / "frozen.joblib"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("immutable-test-artifact")

    result = evaluate_readiness(
        _config(
            strict=True,
            paths=("models/frozen.joblib",),
        ),
        project_root=tmp_path,
    )
    assert result["ready"] is True
    assert result["governance"][
        "readiness_check_does_not_trigger_training"
    ] is True


def test_non_strict_mode_is_available_for_local_debugging(
    tmp_path: Path,
) -> None:
    result = evaluate_readiness(
        _config(
            strict=False,
            paths=("missing.file",),
        ),
        project_root=tmp_path,
    )
    assert result["ready"] is True
    assert result["missing_required_paths"] == ["missing.file"]
