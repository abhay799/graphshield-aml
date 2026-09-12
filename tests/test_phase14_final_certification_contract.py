from pathlib import Path


def test_phase14_certifier_exists() -> None:
    assert Path(
        "src/validation/phase14_final_certification.py"
    ).exists()


def test_release_readiness_module_exists() -> None:
    assert Path(
        "src/enterprise/phase14_release_readiness.py"
    ).exists()
