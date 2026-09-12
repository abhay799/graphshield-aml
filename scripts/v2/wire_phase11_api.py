from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "src" / "api" / "app.py"

MARKER = "# GraphShield Phase 11 explainability routes"

BLOCK = f"""
{MARKER}
from api.explainability_routes import router as phase11_explainability_router
app.include_router(phase11_explainability_router)
"""


def main() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(APP_PATH)

    text = APP_PATH.read_text(encoding="utf-8")

    if MARKER in text:
        print("PHASE11_API_WIRING=ALREADY_PRESENT")
        return

    if "app = FastAPI(" not in text and "app=FastAPI(" not in text:
        raise RuntimeError(
            "Could not verify a FastAPI 'app' instance in src/api/app.py."
        )

    APP_PATH.write_text(
        text.rstrip() + "\n\n" + BLOCK.lstrip(),
        encoding="utf-8",
    )

    print("PHASE11_API_WIRING=ADDED")


if __name__ == "__main__":
    main()
