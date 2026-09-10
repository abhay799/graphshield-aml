from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v1.parquet"
)


def main():

    print("=" * 75)
    print("GraphShield AML - Transaction Feature Validation")
    print("=" * 75)

    if not FEATURE_PATH.exists():

        print("\nERROR: Feature dataset missing.")
        return

    lf = pl.scan_parquet(
        FEATURE_PATH
    )

    # --------------------------------------------------
    # Dataset size
    # --------------------------------------------------

    row_count = (
        lf.select(
            pl.len()
        )
        .collect()
        .item()
    )

    print("\n--- ROW COUNT ---")

    print(
        f"Transactions: {row_count:,}"
    )

    # --------------------------------------------------
    # Feature nulls
    # --------------------------------------------------

    feature_columns = [
        "hour_of_day",
        "day_of_week",
        "is_weekend",
        "same_bank",
        "cross_bank",
        "same_currency",
        "cross_currency",
        "log_amount_paid",
        "log_amount_received",
        "amount_difference",
    ]

    print("\n--- FEATURE NULL CHECK ---")

    nulls = (
        lf.select(
            [
                pl.col(column)
                .null_count()
                .alias(column)

                for column
                in feature_columns
            ]
        )
        .collect()
    )

    for column in feature_columns:

        count = nulls[column][0]

        status = (
            "PASS"
            if count == 0
            else "WARNING"
        )

        print(
            f"{column:<25}"
            f"{count:>10,} "
            f"[{status}]"
        )

    # --------------------------------------------------
    # Boolean feature checks
    # --------------------------------------------------

    print("\n--- BINARY FEATURE VALIDATION ---")

    binary_columns = [
        "is_weekend",
        "same_bank",
        "cross_bank",
        "same_currency",
        "cross_currency",
    ]

    for column in binary_columns:

        values = (
            lf.select(
                pl.col(column)
                .unique()
                .sort()
            )
            .collect()
        )

        print(
            f"{column:<25}: "
            f"{values[column].to_list()}"
        )

    # --------------------------------------------------
    # Hour range
    # --------------------------------------------------

    print("\n--- TIME FEATURE RANGE ---")

    time_range = (
        lf.select(
            [
                pl.col("hour_of_day")
                .min()
                .alias("min_hour"),

                pl.col("hour_of_day")
                .max()
                .alias("max_hour"),

                pl.col("day_of_week")
                .min()
                .alias("min_day"),

                pl.col("day_of_week")
                .max()
                .alias("max_day"),
            ]
        )
        .collect()
    )

    print(time_range)

    # --------------------------------------------------
    # Label preservation
    # --------------------------------------------------

    print("\n--- LABEL DISTRIBUTION ---")

    labels = (
        lf.group_by(
            "is_laundering"
        )
        .agg(
            pl.len()
            .alias("transactions")
        )
        .sort(
            "is_laundering"
        )
        .collect()
    )

    print(labels)

    # --------------------------------------------------
    # Preview
    # --------------------------------------------------

    print("\n--- FEATURE PREVIEW ---")

    print(
        lf.select(
            [
                "transaction_id",
                "event_ts",
                "amount_paid",
                "payment_format",
                "hour_of_day",
                "day_of_week",
                "is_weekend",
                "cross_bank",
                "cross_currency",
                "log_amount_paid",
                "is_laundering",
            ]
        )
        .head(10)
        .collect()
    )

    print("\n" + "=" * 75)
    print("FEATURE VALIDATION COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    main()