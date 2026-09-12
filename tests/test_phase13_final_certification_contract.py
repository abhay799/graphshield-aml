from pathlib import Path


def test_phase13_final_certification_module_exists() -> None:
    assert Path("src/validation/phase13_final_certification.py").exists()


def test_phase13_router_is_wired_into_app_source() -> None:
    text = Path("src/api/app.py").read_text(encoding="utf-8")
    assert "from api.phase13_routes import router as phase13_governance_router" in text
    assert "app.include_router(phase13_governance_router)" in text
