from pathlib import Path


def test_phase15_final_release_gate_exists() -> None:
    assert Path(
        "src/reliability/phase15_final_release_gate.py"
    ).exists()


def test_phase15_final_certifier_exists() -> None:
    assert Path(
        "src/validation/phase15_final_certification.py"
    ).exists()
