from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SILVER_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "silver"
    / "transactions.parquet"
)


EXPECTED_COLUMNS = [
    "transaction_id",
    "event_ts",
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount_received",
    "receiving_currency",
    "amount_paid",
    "payment_currency",
    "payment_format",
    "is_laundering",
    "source_row_number",
    "source_dataset",
]


def main():

    print("=" * 70)
    print("GraphShield AML - Silver Dataset Validation")
    print("=" * 70)

    if not SILVER_PATH.exists():

        print("\nERROR:")
        print("Silver dataset not found.")

        print(SILVER_PATH)

        return

    print("\nSilver dataset:")
    print(SILVER_PATH)

    lf = pl.scan_parquet(
        SILVER_PATH
    )

    # ======================================================
    # Schema
    # ======================================================

    schema = lf.collect_schema()

    print("\n--- SCHEMA ---")

    for column in schema.names():

        print(
            f"{column:<25} "
            f"{schema[column]}"
        )

    # ======================================================
    # Column validation
    # ======================================================

    print("\n--- COLUMN VALIDATION ---")

    actual_columns = schema.names()

    if actual_columns == EXPECTED_COLUMNS:

        print("PASS: Canonical columns match.")

    else:

        print("FAIL: Column mismatch.")

        print("\nExpected:")
        print(EXPECTED_COLUMNS)

        print("\nActual:")
        print(actual_columns)

    # ======================================================
    # Row count
    # ======================================================

    row_count = (
        lf.select(
            pl.len()
            .alias("rows")
        )
        .collect()
        .item()
    )

    print("\n--- ROW COUNT ---")

    print(
        f"Silver rows: {row_count:,}"
    )

    # ======================================================
    # Transaction ID uniqueness
    # ======================================================

    unique_ids = (
        lf.select(
            pl.col("transaction_id")
            .n_unique()
            .alias("unique_ids")
        )
        .collect()
        .item()
    )

    print("\n--- TRANSACTION ID ---")

    print(
        f"Rows       : {row_count:,}"
    )

    print(
        f"Unique IDs : {unique_ids:,}"
    )

    if row_count == unique_ids:

        print("PASS: transaction_id is unique.")

    else:

        print("FAIL: Duplicate transaction IDs detected.")

    # ======================================================
    # Critical nulls
    # ======================================================

    critical_columns = [
        "transaction_id",
        "event_ts",
        "from_bank",
        "from_account",
        "to_bank",
        "to_account",
        "is_laundering",
    ]

    print("\n--- CRITICAL NULL CHECK ---")

    nulls = (
        lf.select(
            [
                pl.col(column)
                .null_count()
                .alias(column)

                for column in critical_columns
            ]
        )
        .collect()
    )

    for column in critical_columns:

        count = nulls[column][0]

        status = (
            "PASS"
            if count == 0
            else "FAIL"
        )

        print(
            f"{column:<25}: "
            f"{count:>8,} "
            f"[{status}]"
        )

    # ======================================================
    # Label distribution
    # ======================================================

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

    # ======================================================
    # Preview
    # ======================================================

    print("\n--- FIRST 5 TRANSACTIONS ---")

    preview = (
        lf.head(5)
        .collect()
    )

    print(preview)

    print("\n" + "=" * 70)
    print("SILVER VALIDATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()