from __future__ import annotations

import json
import math
from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_PATH = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
    / "unified_champion_manifest.json"
)

FEATURE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

ENTITY_MAP_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "entities"
    / "account_entity_map.parquet"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
)

RISK_QUEUE_PATH = (
    OUTPUT_DIR
    / "risk_queue_full.parquet"
)

CASE_QUEUE_PATH = (
    OUTPUT_DIR
    / "case_queue.parquet"
)

QUEUE_PROVENANCE_PATH = (
    OUTPUT_DIR
    / "case_queue_provenance.json"
)


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"STOP: {label} does not exist:\n{path}"
        )

    if not path.is_file():
        raise RuntimeError(
            f"STOP: {label} is not a file:\n{path}"
        )


def load_champion_manifest() -> dict:
    require_file(
        MANIFEST_PATH,
        "Unified champion manifest",
    )

    manifest = json.loads(
        MANIFEST_PATH.read_text(
            encoding="utf-8"
        )
    )

    required_fields = [
        "model_name",
        "selection_source",
        "selected_on_split",
        "selection_metric",
        "test_used_for_selection",
        "prediction_artifact",
        "prediction_split",
        "score_column",
        "queue_capacity_fraction",
        "purpose",
        "autonomous_regulatory_action",
    ]

    missing = [
        field
        for field in required_fields
        if field not in manifest
    ]

    if missing:
        raise RuntimeError(
            "STOP: Champion manifest is missing "
            f"required fields: {missing}"
        )

    if manifest["selected_on_split"] != "validation":
        raise RuntimeError(
            "STOP: Champion must be selected "
            "on validation."
        )

    if manifest["test_used_for_selection"] is not False:
        raise RuntimeError(
            "STOP: Test data must not be used "
            "for model selection."
        )

    if manifest["prediction_split"] != "test":
        raise RuntimeError(
            "STOP: Case queue must be built "
            "from frozen test predictions."
        )

    if (
        manifest["autonomous_regulatory_action"]
        is not False
    ):
        raise RuntimeError(
            "STOP: Autonomous regulatory action "
            "must remain disabled."
        )

    capacity = float(
        manifest["queue_capacity_fraction"]
    )

    if not (0.0 < capacity <= 1.0):
        raise RuntimeError(
            "STOP: queue_capacity_fraction must "
            "be in the interval (0, 1]."
        )

    artifact_rel = Path(
        manifest["prediction_artifact"]
    )

    if artifact_rel.is_absolute():
        raise RuntimeError(
            "STOP: prediction_artifact must be "
            "project-relative."
        )

    project_root_resolved = (
        PROJECT_ROOT.resolve()
    )

    prediction_path = (
        PROJECT_ROOT
        / artifact_rel
    ).resolve()

    try:
        prediction_path.relative_to(
            project_root_resolved
        )
    except ValueError as exc:
        raise RuntimeError(
            "STOP: prediction_artifact resolves "
            "outside the project root."
        ) from exc

    require_file(
        prediction_path,
        "Champion prediction artifact",
    )

    manifest["_prediction_path"] = (
        prediction_path
    )

    manifest["_review_fraction"] = (
        capacity
    )

    return manifest


def validate_prediction_schema(
    prediction_path: Path,
    score_column: str,
) -> None:
    schema = pl.read_parquet_schema(
        prediction_path
    )

    required = {
        "transaction_id",
        score_column,
    }

    missing = sorted(
        required - set(schema)
    )

    if missing:
        raise RuntimeError(
            "STOP: Prediction artifact is "
            f"missing columns: {missing}"
        )


def validate_supporting_artifacts() -> None:
    require_file(
        FEATURE_PATH,
        "Graph modeling feature artifact",
    )

    require_file(
        ENTITY_MAP_PATH,
        "Account/entity mapping artifact",
    )

    feature_schema = pl.read_parquet_schema(
        FEATURE_PATH
    )

    required_features = {
        "transaction_id",
        "split",
        "event_ts",
        "from_account_key",
        "to_account_key",
        "amount_paid",
        "payment_currency",
        "payment_format",
    }

    missing_features = sorted(
        required_features
        - set(feature_schema)
    )

    if missing_features:
        raise RuntimeError(
            "STOP: Feature artifact is missing "
            f"columns: {missing_features}"
        )

    entity_schema = pl.read_parquet_schema(
        ENTITY_MAP_PATH
    )

    required_entity = {
        "account_key",
        "entity_id",
    }

    missing_entity = sorted(
        required_entity
        - set(entity_schema)
    )

    if missing_entity:
        raise RuntimeError(
            "STOP: Entity map is missing "
            f"columns: {missing_entity}"
        )


def main() -> None:
    print("=" * 90)
    print(
        "GraphShield AML - "
        "Manifest-Locked Investigation Case Queue"
    )
    print("=" * 90)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest = load_champion_manifest()

    prediction_path = manifest[
        "_prediction_path"
    ]

    score_column = str(
        manifest["score_column"]
    )

    model_name = str(
        manifest["model_name"]
    )

    review_fraction = float(
        manifest["_review_fraction"]
    )

    validate_prediction_schema(
        prediction_path,
        score_column,
    )

    validate_supporting_artifacts()

    print("\nChampion manifest:")
    print(MANIFEST_PATH)

    print("\nModel:")
    print(model_name)

    print("\nSelected on:")
    print(manifest["selected_on_split"])

    print("\nSelection metric:")
    print(manifest["selection_metric"])

    print("\nTest used for selection:")
    print(manifest["test_used_for_selection"])

    print("\nPrediction split:")
    print(manifest["prediction_split"])

    print("\nPrediction source:")
    print(prediction_path)

    print("\nScore column:")
    print(score_column)

    predictions = (
        pl.scan_parquet(
            prediction_path
        )
        .select(
            [
                pl.col(
                    "transaction_id"
                ),

                pl.col(
                    score_column
                )
                .cast(
                    pl.Float64
                )
                .alias(
                    "risk_score"
                ),
            ]
        )
    )

    prediction_stats = (
        predictions
        .select(
            [
                pl.len()
                .alias("rows"),

                pl.col(
                    "transaction_id"
                )
                .n_unique()
                .alias("unique_transactions"),

                pl.col(
                    "risk_score"
                )
                .null_count()
                .alias("null_scores"),

                (
                    ~pl.col(
                        "risk_score"
                    )
                    .is_finite()
                )
                .sum()
                .alias(
                    "nonfinite_scores"
                ),
            ]
        )
        .collect()
        .row(
            0,
            named=True,
        )
    )

    if prediction_stats["rows"] == 0:
        raise RuntimeError(
            "STOP: Prediction artifact is empty."
        )

    if (
        prediction_stats["rows"]
        != prediction_stats[
            "unique_transactions"
        ]
    ):
        raise RuntimeError(
            "STOP: Prediction artifact contains "
            "duplicate transaction_id values."
        )

    if prediction_stats["null_scores"] != 0:
        raise RuntimeError(
            "STOP: Prediction artifact contains "
            "null risk scores."
        )

    if (
        prediction_stats[
            "nonfinite_scores"
        ]
        != 0
    ):
        raise RuntimeError(
            "STOP: Prediction artifact contains "
            "non-finite risk scores."
        )

    features = (
        pl.scan_parquet(
            FEATURE_PATH
        )
        .filter(
            pl.col("split")
            == manifest[
                "prediction_split"
            ]
        )
        .select(
            [
                "transaction_id",
                "event_ts",
                "from_account_key",
                "to_account_key",
                "amount_paid",
                "payment_currency",
                "payment_format",
            ]
        )
    )

    mapping = (
        pl.scan_parquet(
            ENTITY_MAP_PATH
        )
        .select(
            [
                "account_key",
                "entity_id",
            ]
        )
        .unique(
            subset=[
                "account_key",
            ],
            keep="first",
        )
    )

    sender_map = (
        mapping
        .select(
            [
                pl.col(
                    "account_key"
                )
                .alias(
                    "from_account_key"
                ),

                pl.col(
                    "entity_id"
                )
                .alias(
                    "from_entity_id"
                ),
            ]
        )
    )

    receiver_map = (
        mapping
        .select(
            [
                pl.col(
                    "account_key"
                )
                .alias(
                    "to_account_key"
                ),

                pl.col(
                    "entity_id"
                )
                .alias(
                    "to_entity_id"
                ),
            ]
        )
    )

    queue = (
        predictions
        .join(
            features,
            on="transaction_id",
            how="inner",
        )
        .join(
            sender_map,
            on="from_account_key",
            how="left",
        )
        .join(
            receiver_map,
            on="to_account_key",
            how="left",
        )
        .sort(
            [
                "risk_score",
                "transaction_id",
            ],
            descending=[
                True,
                False,
            ],
        )
        .with_row_index(
            "risk_rank",
            offset=1,
        )
    )

    joined_rows = (
        queue
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    prediction_rows = int(
        prediction_stats["rows"]
    )

    if joined_rows != prediction_rows:
        raise RuntimeError(
            "STOP: Prediction → feature join "
            "did not preserve every prediction. "
            f"Predictions={prediction_rows:,}, "
            f"joined={joined_rows:,}."
        )

    review_count = max(
        1,
        int(
            math.ceil(
                joined_rows
                * review_fraction
            )
        ),
    )

    manifest_rel = (
        MANIFEST_PATH
        .relative_to(
            PROJECT_ROOT
        )
        .as_posix()
    )

    prediction_rel = (
        prediction_path
        .relative_to(
            PROJECT_ROOT.resolve()
        )
        .as_posix()
    )

    queue = (
        queue
        .with_columns(
            [
                (
                    1.0
                    - (
                        (
                            pl.col(
                                "risk_rank"
                            )
                            - 1
                        )
                        / joined_rows
                    )
                )
                .alias(
                    "risk_percentile"
                ),

                pl.lit(
                    model_name
                )
                .alias(
                    "source_model"
                ),

                pl.lit(
                    manifest[
                        "selected_on_split"
                    ]
                )
                .alias(
                    "model_selected_on_split"
                ),

                pl.lit(
                    manifest[
                        "selection_metric"
                    ]
                )
                .alias(
                    "model_selection_metric"
                ),

                pl.lit(
                    manifest[
                        "prediction_split"
                    ]
                )
                .alias(
                    "prediction_split"
                ),

                pl.lit(
                    prediction_rel
                )
                .alias(
                    "prediction_artifact"
                ),

                pl.lit(
                    manifest_rel
                )
                .alias(
                    "champion_manifest"
                ),

                pl.concat_str(
                    [
                        pl.lit(
                            "CASE_"
                        ),
                        pl.col(
                            "transaction_id"
                        ),
                    ]
                )
                .alias(
                    "case_id"
                ),
            ]
        )
    )

    queue.sink_parquet(
        RISK_QUEUE_PATH,
        compression="zstd",
    )

    cases = (
        queue
        .filter(
            pl.col(
                "risk_rank"
            )
            <= review_count
        )
        .with_columns(
            [
                pl.lit(
                    "OPEN"
                )
                .alias(
                    "case_status"
                ),

                pl.lit(
                    review_fraction
                )
                .alias(
                    "review_capacity"
                ),
            ]
        )
    )

    cases.sink_parquet(
        CASE_QUEUE_PATH,
        compression="zstd",
    )

    provenance = {
        "champion_manifest": (
            manifest_rel
        ),
        "model_name": (
            model_name
        ),
        "selected_on_split": (
            manifest[
                "selected_on_split"
            ]
        ),
        "selection_metric": (
            manifest[
                "selection_metric"
            ]
        ),
        "test_used_for_selection": (
            manifest[
                "test_used_for_selection"
            ]
        ),
        "prediction_split": (
            manifest[
                "prediction_split"
            ]
        ),
        "prediction_artifact": (
            prediction_rel
        ),
        "score_column": (
            score_column
        ),
        "queue_capacity_fraction": (
            review_fraction
        ),
        "prediction_rows": (
            prediction_rows
        ),
        "joined_rows": (
            joined_rows
        ),
        "cases_created": (
            review_count
        ),
        "purpose": (
            manifest[
                "purpose"
            ]
        ),
        "autonomous_regulatory_action": (
            manifest[
                "autonomous_regulatory_action"
            ]
        ),
    }

    QUEUE_PROVENANCE_PATH.write_text(
        json.dumps(
            provenance,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"\nTest transactions: "
        f"{joined_rows:,}"
    )

    print(
        f"Review capacity: "
        f"{review_fraction:.1%}"
    )

    print(
        f"Cases created: "
        f"{review_count:,}"
    )

    print("\nCreated:")
    print(RISK_QUEUE_PATH)
    print(CASE_QUEUE_PATH)
    print(QUEUE_PROVENANCE_PATH)

    print(
        "\nCASE QUEUE MANIFEST LOCK: PASS"
    )


if __name__ == "__main__":
    main()
