from datetime import datetime, timezone
from pathlib import Path
import csv
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REPORT_DIR = PROJECT_ROOT / "reports" / "modeling"

OUTPUT_REPORT = REPORT_DIR / "phase2_artifact_sizes.csv"

ARTIFACTS = [
    {
        "name": "Phase 2 split model dataset",
        "path": PROJECT_ROOT
        / "data"
        / "processed"
        / "gold"
        / "model_features_v1_split.parquet",
        "required": True,
    },
    {
        "name": "Phase 2 entity overlap audit",
        "path": REPORT_DIR / "phase2_entity_overlap_audit.csv",
        "required": True,
    },
    {
        "name": "Phase 2 leakage console output",
        "path": REPORT_DIR / "phase2_leakage_console.txt",
        "required": False,
    },
    {
        "name": "Phase 2 temporal split report",
        "path": REPORT_DIR / "phase2_temporal_split_report.csv",
        "required": False,
    },
]


def format_bytes(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)

    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{size_bytes} B"


def main() -> None:
    print("=" * 88)
    print("GraphShield AML - Phase 2 Artifact Size Audit")
    print("=" * 88)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    missing_required = []

    print()

    for artifact in ARTIFACTS:
        path = artifact["path"]
        exists = path.exists()

        if exists:
            size_bytes = path.stat().st_size
            modified_utc = datetime.fromtimestamp(
                path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()

            status = "PASS"

            print(f"{artifact['name']}:")
            print(f"  Status: {status}")
            print(f"  Path: {path}")
            print(f"  Size: {format_bytes(size_bytes)}")
            print()

        else:
            size_bytes = None
            modified_utc = None
            status = "MISSING"

            print(f"{artifact['name']}:")
            print(f"  Status: {status}")
            print(f"  Expected path: {path}")
            print()

            if artifact["required"]:
                missing_required.append(artifact["name"])

        rows.append(
            {
                "artifact_name": artifact["name"],
                "required": artifact["required"],
                "status": status,
                "path": str(path),
                "size_bytes": size_bytes,
                "size_human_readable": (
                    format_bytes(size_bytes)
                    if size_bytes is not None
                    else None
                ),
                "last_modified_utc": modified_utc,
            }
        )

    with OUTPUT_REPORT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "artifact_name",
                "required",
                "status",
                "path",
                "size_bytes",
                "size_human_readable",
                "last_modified_utc",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print("--- REPORT CREATED ---")
    print(OUTPUT_REPORT)

    if missing_required:
        print("\nPHASE 2 ARTIFACT AUDIT: FAILED")
        print("\nMissing required artifacts:")
        for artifact_name in missing_required:
            print(f"  - {artifact_name}")
        sys.exit(1)

    print("\n" + "=" * 88)
    print("PHASE 2 ARTIFACT AUDIT: PASS")
    print("=" * 88)


if __name__ == "__main__":
    main()