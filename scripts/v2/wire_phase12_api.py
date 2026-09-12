from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "src" / "api" / "app.py"

MARKER = "# GraphShield Phase 12 investigation routes"

BLOCK = f"""
{MARKER}
from api.phase12_routes import router as phase12_investigation_router
app.include_router(phase12_investigation_router)
"""


def main() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(APP_PATH)

    text = APP_PATH.read_text(
        encoding="utf-8"
    )

    if MARKER in text:
        print(
            "PHASE12_API_WIRING=ALREADY_PRESENT"
        )
        return

    if (
        "app = FastAPI("
        not in text
        and "app=FastAPI("
        not in text
    ):
        raise RuntimeError(
            "Could not verify FastAPI app instance."
        )

    APP_PATH.write_text(
        text.rstrip()
        + "\n\n"
        + BLOCK.lstrip(),
        encoding="utf-8",
    )

    print(
        "PHASE12_API_WIRING=ADDED"
    )


if __name__ == "__main__":
    main()
