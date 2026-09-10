from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs" / "v2" / "training"


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_text(args: list[str]) -> str | None:
    try:
        p = subprocess.run(
            args,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if p.returncode != 0:
        return None
    return p.stdout.strip() or None


def git_info() -> dict:
    commit = run_text(["git", "rev-parse", "HEAD"])
    branch = run_text(["git", "branch", "--show-current"])
    status = run_text(["git", "status", "--porcelain"])
    return {
        "commit": commit,
        "branch": branch,
        "dirty": bool(status),
    }


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def find_unique_input(filename: str) -> Path:
    candidates = [
        p for p in (PROJECT_ROOT / "data" / "processed").rglob(filename)
        if not any(
            token in str(p).lower()
            for token in ("before_", "backup", "stale", ".bak")
        )
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected exactly one authoritative {filename}; found {len(candidates)}: "
            + ", ".join(str(p) for p in candidates)
        )
    return candidates[0]


def split_summary(event_path: Path) -> dict:
    schema = pl.read_parquet_schema(event_path)
    if "split" not in schema:
        return {"available": False, "reason": "No split column in TGN event artifact."}

    aggregations = [pl.len().alias("events")]
    if "event_ts" in schema:
        aggregations.extend(
            [
                pl.col("event_ts").min().alias("min_event_ts"),
                pl.col("event_ts").max().alias("max_event_ts"),
            ]
        )

    df = (
        pl.scan_parquet(event_path)
        .group_by("split")
        .agg(aggregations)
        .sort("split")
        .collect()
    )

    rows = df.to_dicts()
    return {
        "available": True,
        "rows": rows,
        "sha256": sha256_json(rows),
    }


def hardware_info() -> dict:
    info = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "torch": package_version("torch"),
        "polars": package_version("polars"),
        "gpu": None,
        "nvcc": None,
    }

    if shutil.which("nvidia-smi"):
        info["gpu"] = run_text(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ]
        )

    if shutil.which("nvcc"):
        info["nvcc"] = run_text(["nvcc", "--version"])

    return info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=["smoke", "full"])
    parser.add_argument(
        "--hash-inputs",
        action="store_true",
        help="Compute full SHA256 hashes of the TGN parquet inputs.",
    )
    args = parser.parse_args()

    config_path = CONFIG_DIR / f"tgn_{args.profile}.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    profile_name = str(config.get("profile", f"tgn_{args.profile}"))

    event_path = find_unique_input("tgn_events.parquet")
    node_path = find_unique_input("tgn_node_mapping.parquet")

    inputs = {}
    for label, path in (("events", event_path), ("node_mapping", node_path)):
        stat = path.stat()
        inputs[label] = {
            "path": str(path.relative_to(PROJECT_ROOT)),
            "size_bytes": stat.st_size,
            "sha256": sha256_file(path) if args.hash_inputs else None,
        }

    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "profile": profile_name,
        "config_path": str(config_path.relative_to(PROJECT_ROOT)),
        "config_sha256": sha256_file(config_path),
        "config": config,
        "git": git_info(),
        "runtime": hardware_info(),
        "inputs": inputs,
        "split_summary": split_summary(event_path),
        "full_input_hashes_computed": bool(args.hash_inputs),
    }

    out_dir = PROJECT_ROOT / "reports" / "v2" / "training" / profile_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "run_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    print(f"MANIFEST={out_path}")
    print(f"EVENT_INPUT={event_path}")
    print(f"NODE_INPUT={node_path}")
    print(f"INPUT_HASHES={'FULL' if args.hash_inputs else 'DEFERRED'}")
    print("GRAPHSHIELD_TGN_MANIFEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
