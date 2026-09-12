from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "src" / "api" / "app.py"

IMPORT_ROUTER = (
    "from api.phase14_routes import router as phase14_enterprise_router"
)
IMPORT_SECURITY = (
    "from enterprise.phase14_runtime import install_enterprise_security"
)
INCLUDE_ROUTER = "app.include_router(phase14_enterprise_router)"
INSTALL_SECURITY = "install_enterprise_security(app)"
MARKER = "# Phase 14 enterprise platform wiring"


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    if (
        IMPORT_ROUTER in text
        and IMPORT_SECURITY in text
        and INCLUDE_ROUTER in text
        and INSTALL_SECURITY in text
    ):
        print("Phase 14 API already wired.")
        print("GRAPHSHIELD_PHASE14_API_WIRING=PASS")
        return

    block = (
        "\n\n"
        f"{MARKER}\n"
        f"{IMPORT_ROUTER}\n"
        f"{IMPORT_SECURITY}\n"
        f"{INCLUDE_ROUTER}\n"
        f"{INSTALL_SECURITY}\n"
    )

    APP_PATH.write_text(
        text.rstrip() + block,
        encoding="utf-8",
    )

    print(f"Wired Phase 14 enterprise runtime into: {APP_PATH}")
    print("GRAPHSHIELD_PHASE14_API_WIRING=PASS")


if __name__ == "__main__":
    main()
