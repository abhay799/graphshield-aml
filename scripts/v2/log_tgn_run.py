from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import mlflow


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Log a GraphShield v2 TGN run to MLflow."
    )
    parser.add_argument("profile", choices=["smoke", "full"])
    parser.add_argument(
        "--include-checkpoint",
        action="store_true",
        help="Upload the TGN checkpoint as an MLflow artifact.",
    )
    args = parser.parse_args()

    profile_name = f"tgn_{args.profile}"
    run_dir = PROJECT_ROOT / "reports" / "v2" / "training" / profile_name
    manifest_path = run_dir / "run_manifest.json"
    metrics_path = run_dir / "tgn_metrics.json"
    checkpoint_path = (
        PROJECT_ROOT / "models" / "v2" / profile_name / "tgn_risk.pt"
    )

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest missing: {manifest_path}. Build it before MLflow logging."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    tracking_uri = os.getenv(
        "MLFLOW_TRACKING_URI",
        "http://127.0.0.1:5000",
    )
    experiment = os.getenv(
        "MLFLOW_EXPERIMENT_NAME",
        "graphshield-v2-tgn",
    )

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)

    git = manifest.get("git", {})
    runtime = manifest.get("runtime", {})
    config = manifest.get("config", {})
    env_config = config.get("env", {}) or {}

    run_name = (
        f"{profile_name}-"
        f"{str(git.get('commit') or 'nogit')[:8]}"
    )

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags(
            {
                "project": "GraphShield AML",
                "phase": "8.5",
                "step": "10",
                "profile": profile_name,
                "git_commit": str(git.get("commit") or ""),
                "git_branch": str(git.get("branch") or ""),
                "git_dirty": str(bool(git.get("dirty"))).lower(),
                "input_hashes": (
                    "full"
                    if manifest.get("full_input_hashes_computed")
                    else "deferred"
                ),
            }
        )

        params = {
            "seed": config.get("seed"),
            "device_request": config.get("device"),
            "python": runtime.get("python"),
            "torch": runtime.get("torch"),
            "polars": runtime.get("polars"),
        }
        params.update(env_config)

        for key, value in params.items():
            if value is not None:
                mlflow.log_param(str(key), value)

        mlflow.log_artifact(str(manifest_path), artifact_path="manifest")

        if metrics_path.exists():
            report = json.loads(metrics_path.read_text(encoding="utf-8"))

            metric_map = {
                "best_validation_ap": report.get("best_validation_ap"),
                "validation_ap": (
                    report.get("final_validation", {})
                    .get("average_precision")
                ),
                "validation_recall_at_1pct": (
                    report.get("final_validation", {})
                    .get("recall_at_top_1pct")
                ),
                "test_ap": (
                    report.get("final_test", {})
                    .get("average_precision")
                ),
                "test_recall_at_1pct": (
                    report.get("final_test", {})
                    .get("recall_at_top_1pct")
                ),
            }

            for key, value in metric_map.items():
                if numeric(value):
                    mlflow.log_metric(key, float(value))

            mlflow.log_artifact(str(metrics_path), artifact_path="metrics")

        if args.include_checkpoint:
            if not checkpoint_path.exists():
                raise FileNotFoundError(
                    f"Checkpoint missing: {checkpoint_path}"
                )
            mlflow.log_artifact(
                str(checkpoint_path),
                artifact_path="checkpoint",
            )

        print(f"MLFLOW_TRACKING_URI={tracking_uri}")
        print(f"MLFLOW_EXPERIMENT={experiment}")
        print(f"MLFLOW_RUN_ID={run.info.run_id}")

    print("GRAPHSHIELD_TGN_MLFLOW=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
