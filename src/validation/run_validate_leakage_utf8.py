from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

TARGET = (
    PROJECT_ROOT
    / "src"
    / "validation"
    / "validate_leakage.py"
)


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(
            f"Leakage validator not found:\n{TARGET}"
        )

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, str(TARGET)],
        cwd=PROJECT_ROOT,
        env=env,
    )

    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
