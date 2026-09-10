from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1_split.parquet"
)


# ==========================================================
# Columns that must NEVER enter the model
# ==========================================================

EXCLUDED_COLUMNS = {
    "transaction_id",
    "event_ts",
    "from_account_key",
    "to_account_key",

    # Validation/debug timestamps
    "sender_prev_event_ts",
    "receiver_prev_event_ts",
    "sender_last_inbound_ts_1h",

    # Split information
    "split",

    # Target
    "is_laundering",
}


CATEGORICAL_COLUMNS = [
    "payment_format",
    "payment_currency",
    "receiving_currency",
]


def main():

    print("=" * 90)
    print("GraphShield AML - Phase 3.1 Dataset & Split Analysis")
    print("=" * 90)

    if not DATA_PATH.exists():
        print("\nERROR: Model split dataset not found:")
        print(DATA_PATH)
        return

    lf = pl.scan_parquet(DATA_PATH)

    schema = lf.collect_schema()

    # ======================================================
    # Dataset size
    # ======================================================

    overall = (
        lf.select(
            [
                pl.len().alias("transactions"),

                pl.col("is_laundering")
                .sum()
                .alias("positives"),

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
                pl.col("positives")
                / pl.col("transactions")
                * 100
            )
            .alias("positive_rate_percent")
        )
        .collect()
    )

    print("\n--- OVERALL DATASET ---")
    print(overall)

    # ======================================================
    # Split analysis
    # ======================================================

    split_stats = (
        lf.group_by("split")
        .agg(
            [
                pl.len()
                .alias("transactions"),

                pl.col("is_laundering")
                .sum()
                .alias("positives"),

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
                pl.col("positives")
                / pl.col("transactions")
            )
            .alias("positive_rate"),

            (
                pl.col("positives")
                / pl.col("transactions")
                * 100
            )
            .alias("positive_rate_percent"),
        )
        .sort("start")
        .collect()
    )

    print("\n--- SPLIT DISTRIBUTION ---")
    print(split_stats)

    # ======================================================
    # Positive / negative ratio
    # ======================================================

    imbalance = (
        lf.group_by("split")
        .agg(
            [
                pl.col("is_laundering")
                .sum()
                .alias("positives"),

                (
                    pl.len()
                    - pl.col("is_laundering").sum()
                )
                .alias("negatives"),
            ]
        )
        .with_columns(
            (
                pl.col("negatives")
                / pl.col("positives")
            )
            .alias("negative_to_positive_ratio")
        )
        .collect()
    )

    print("\n--- CLASS IMBALANCE ---")
    print(imbalance)

    # ======================================================
    # Target integrity
    # ======================================================

    target_values = (
        lf.select("is_laundering")
        .unique()
        .sort("is_laundering")
        .collect()
    )

    print("\n--- TARGET VALUES ---")
    print(target_values)

    # ======================================================
    # Feature groups
    # ======================================================

    all_columns = list(schema.names())

    model_features = [
        column
        for column in all_columns
        if column not in EXCLUDED_COLUMNS
    ]

    numerical_features = [
        column
        for column in model_features
        if column not in CATEGORICAL_COLUMNS
    ]

    print("\n--- FEATURE INVENTORY ---")

    print(f"Total dataset columns: {len(all_columns)}")
    print(f"Model features:        {len(model_features)}")
    print(f"Numerical features:    {len(numerical_features)}")
    print(f"Categorical features:  {len(CATEGORICAL_COLUMNS)}")

    print("\nCategorical:")
    for column in CATEGORICAL_COLUMNS:
        print(f"  - {column}")

    # ======================================================
    # Missing values
    # ======================================================

    print("\n--- MODEL FEATURE NULL COUNTS ---")

    null_counts = (
        lf.select(
            [
                pl.col(column)
                .null_count()
                .alias(column)
                for column in model_features
            ]
        )
        .collect()
    )

    null_summary = []

    for column in model_features:

        count = null_counts[column][0]

        if count > 0:
            null_summary.append(
                (column, count)
            )

    if not null_summary:

        print("No nulls in model features.")

    else:

        for column, count in sorted(
            null_summary,
            key=lambda x: x[1],
            reverse=True,
        ):
            print(
                f"{column:<40} {count:,}"
            )

    # ======================================================
    # No-skill PR-AUC baseline
    # ======================================================

    print("\n--- NO-SKILL BASELINE ---")

    baselines = (
        lf.group_by("split")
        .agg(
            [
                pl.len()
                .alias("rows"),

                pl.col("is_laundering")
                .mean()
                .alias("positive_prevalence"),
            ]
        )
        .with_columns(
            pl.col("positive_prevalence")
            .alias("no_skill_pr_auc")
        )
        .collect()
    )

    print(baselines)

    print(
        "\nFor an imbalanced binary task, "
        "positive prevalence is the approximate "
        "no-skill Average Precision / PR baseline."
    )

    # ======================================================
    # Important leakage exclusions
    # ======================================================

    print("\n--- EXCLUDED FROM ML ---")

    for column in sorted(EXCLUDED_COLUMNS):
        if column in schema:
            print(f"  - {column}")

    print("\n" + "=" * 90)
    print("PHASE 3.1 ANALYSIS COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()