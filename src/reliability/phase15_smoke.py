from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.app import app
from enterprise.phase14_runtime import PROJECT_ROOT

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase15"
    / "production_smoke_v1_report.json"
)


def run_smoke(
    *,
    output_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    client = TestClient(app)

    checks: dict[str, dict[str, Any]] = {}

    for path in (
        "/live",
        "/ready",
        "/deployment",
        "/deployment/integrity",
    ):
        response = client.get(path)
        checks[path] = {
            "status_code": response.status_code,
            "pass": response.status_code == 200,
        }

    passed = all(item["pass"] for item in checks.values())

    report = {
        "schema_version": "phase15_production_smoke_v1",
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "interpretation": {
            "smoke_is_in_process_not_external_production_traffic": True,
            "smoke_does_not_prove_end_to_end_cloud_networking": True,
        },
        "governance": {
            "read_only_smoke_checks_only": True,
            "no_case_mutation": True,
            "no_model_mutation": True,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = run_smoke()
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit("GRAPHSHIELD_PHASE15_PRODUCTION_SMOKE=FAIL")
    print("GRAPHSHIELD_PHASE15_PRODUCTION_SMOKE=PASS")


if __name__ == "__main__":
    main()
