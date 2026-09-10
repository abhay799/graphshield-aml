from pathlib import Path
import json

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1_split.parquet"
)

MANIFEST_PATH = (
    PROJECT_ROOT
    / "reports"
    / "temporal_split_manifest.json"
)


def main():

    print("=" * 80)
    print("GraphShield AML - Temporal Train/Validation/Test Split")
    print("=" * 80)

    lf = pl.scan_parquet(INPUT_PATH)

    # Convert timestamp to integer representation only
    # for obtaining temporal quantiles.
    cutoffs = (
        lf.select(
            [
                pl.col("event_ts")
                .cast(pl.Int64)
                .quantile(
                    0.70,
                    interpolation="nearest",
                )
                .alias("train_cutoff"),

                pl.col("event_ts")
                .cast(pl.Int64)
                .quantile(
                    0.85,
                    interpolation="nearest",
                )
                .alias("validation_cutoff"),
            ]
        )
        .collect()
    )

    train_cutoff = int(
        cutoffs["train_cutoff"][0]
    )

    validation_cutoff = int(
        cutoffs["validation_cutoff"][0]
    )

    print("\nTrain cutoff integer:")
    print(train_cutoff)

    print("\nValidation cutoff integer:")
    print(validation_cutoff)

    # ======================================================
    # Assign chronological split
    # ======================================================

    lf = (
        lf
        .with_columns(
            pl.col("event_ts")
            .cast(pl.Int64)
            .alias("_event_ts_int")
        )
        .with_columns(
            pl.when(
                pl.col("_event_ts_int")
                <= train_cutoff
            )
            .then(pl.lit("train"))

            .when(
                pl.col("_event_ts_int")
                <= validation_cutoff
            )
            .then(pl.lit("validation"))

            .otherwise(
                pl.lit("test")
            )
            .alias("split")
        )
        .drop("_event_ts_int")
    )

    print("\nWriting split dataset...")

    lf.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    # ======================================================
    # Split statistics
    # ======================================================

    stats = (
        pl.scan_parquet(OUTPUT_PATH)
        .group_by("split")
        .agg(
            [
                pl.len()
                .alias("transactions"),

                pl.col("is_laundering")
                .sum()
                .alias(
                    "laundering_transactions"
                ),

                pl.col("event_ts")
                .min()
                .alias("start"),

                pl.col("event_ts")
                .max()
                .alias("end"),
            ]
        )
        .with_columns(
            (
                pl.col("laundering_transactions")
                / pl.col("transactions")
                * 100
            )
            .alias("laundering_rate_percent")
        )
        .sort("start")
        .collect()
    )

    print("\n--- SPLIT SUMMARY ---")
    print(stats)

    manifest = {
        "strategy": "chronological",
        "target_train_fraction": 0.70,
        "target_validation_fraction": 0.15,
        "target_test_fraction": 0.15,
        "train_cutoff_int": train_cutoff,
        "validation_cutoff_int": validation_cutoff,
    }

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nManifest:")
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()