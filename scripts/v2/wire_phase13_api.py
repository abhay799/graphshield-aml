from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "src" / "api" / "app.py"

IMPORT_LINE = "from api.phase13_routes import router as phase13_governance_router"
INCLUDE_LINE = "app.include_router(phase13_governance_router)"
MARKER = "# Phase 13 governance API"


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    if IMPORT_LINE in text and INCLUDE_LINE in text:
        print("Phase 13 API already wired.")
        print("GRAPHSHIELD_PHASE13_API_WIRING=PASS")
        return

    block = (
        "\n\n"
        f"{MARKER}\n"
        f"{IMPORT_LINE}\n"
        f"{INCLUDE_LINE}\n"
    )

    APP_PATH.write_text(text.rstrip() + block, encoding="utf-8")
    print(f"Wired Phase 13 router into: {APP_PATH}")
    print("GRAPHSHIELD_PHASE13_API_WIRING=PASS")


if __name__ == "__main__":
    main()
