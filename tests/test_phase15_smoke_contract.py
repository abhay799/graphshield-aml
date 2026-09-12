from pathlib import Path


def test_phase15_smoke_module_exists() -> None:
    assert Path("src/reliability/phase15_smoke.py").exists()


def test_phase15_reliability_modules_exist() -> None:
    required = (
        "src/reliability/phase15_slo_readiness.py",
        "src/reliability/phase15_failure_modes.py",
        "src/reliability/phase15_recovery_verifier.py",
    )
    for path in required:
        assert Path(path).exists()
