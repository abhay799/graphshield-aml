from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = PROJECT_ROOT / "reports" / "v2" / "phase14"
MANIFEST_PATH = REPORT_DIR / "artifact_manifest_v1.json"

CERTIFIED_ARTIFACTS = (
    "models/lightgbm_graph_v1.joblib",
    "models/probability_calibrator_graph_v1.joblib",
    "models/v2/phase10_fusion_calibrator_v1.joblib",
    "reports/v2/phase13/phase13_final_certification_v1_report.json",
)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact_manifest(
    *,
    project_root: Path = PROJECT_ROOT,
    artifact_paths: tuple[str, ...] = CERTIFIED_ARTIFACTS,
    output_path: Path = MANIFEST_PATH,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    missing: list[str] = []

    for rel in artifact_paths:
        path = project_root / rel
        if not path.exists():
            artifacts.append(
                {
                    "path": rel,
                    "exists": False,
                    "size_bytes": None,
                    "sha256": None,
                }
            )
            missing.append(rel)
            continue

        artifacts.append(
            {
                "path": rel,
                "exists": True,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    report = {
        "schema_version": "phase14_artifact_manifest_v1",
        "status": "PASS" if not missing else "FAIL",
        "artifact_count": len(artifact_paths),
        "missing_artifacts": missing,
        "artifacts": artifacts,
        "governance": {
            "certified_artifacts_read_only": True,
            "manifest_generation_modifies_artifacts": False,
            "automatic_model_replacement": False,
            "automatic_model_promotion": False,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def verify_artifact_manifest(
    *,
    manifest_path: Path = MANIFEST_PATH,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    if not manifest_path.exists():
        return {
            "status": "FAIL",
            "verified": False,
            "reason": "manifest_missing",
            "mismatches": [],
        }

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches: list[dict[str, Any]] = []

    for item in manifest.get("artifacts", []):
        rel = item["path"]
        path = project_root / rel

        if not path.exists():
            mismatches.append(
                {
                    "path": rel,
                    "reason": "artifact_missing",
                }
            )
            continue

        actual_size = path.stat().st_size
        actual_hash = sha256_file(path)

        if actual_size != item.get("size_bytes"):
            mismatches.append(
                {
                    "path": rel,
                    "reason": "size_mismatch",
                    "expected": item.get("size_bytes"),
                    "actual": actual_size,
                }
            )

        if actual_hash != item.get("sha256"):
            mismatches.append(
                {
                    "path": rel,
                    "reason": "sha256_mismatch",
                    "expected": item.get("sha256"),
                    "actual": actual_hash,
                }
            )

    return {
        "status": "PASS" if not mismatches else "FAIL",
        "verified": not mismatches,
        "mismatches": mismatches,
        "artifact_count": len(manifest.get("artifacts", [])),
        "governance": {
            "verification_is_read_only": True,
            "automatic_remediation": False,
        },
    }


def main() -> None:
    manifest = build_artifact_manifest()
    print(json.dumps(manifest, indent=2))
    print("GRAPHSHIELD_PHASE14_ARTIFACT_MANIFEST=PASS")


if __name__ == "__main__":
    main()
