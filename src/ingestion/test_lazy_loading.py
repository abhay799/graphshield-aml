from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "LI-Small_Trans.csv"
)


def main():
    print("=" * 70)
    print("GraphShield AML - Data Quality Validation")
    print("=" * 70)

    # --------------------------------------------------
    # Check dataset existence
    # --------------------------------------------------

    if not DATA_PATH.exists():
        print("\nERROR: Dataset not found.")
        print(DATA_PATH)
        return

    print("\nDataset found:")
    print(DATA_PATH)

    # --------------------------------------------------
    # Lazy CSV loading
    # --------------------------------------------------

    print("\nScanning dataset...")

    lf = pl.scan_csv(DATA_PATH)

    schema = lf.collect_schema()

    columns = schema.names()

    print("\n--- SCHEMA ---")

    for column in columns:
        print(
            f"{column:<25} "
            f"{schema[column]}"
        )

    # --------------------------------------------------
    # Total rows
    # --------------------------------------------------

    total_rows = (
        lf.select(
            pl.len().alias("total_rows")
        )
        .collect()
        .item()
    )

    print("\n--- DATASET SIZE ---")

    print(f"Total rows: {total_rows:,}")
    print(f"Columns   : {len(columns)}")

    # --------------------------------------------------
    # Missing values
    # --------------------------------------------------

    print("\n--- NULL VALUE CHECK ---")

    null_counts = (
        lf.select(
            [
                pl.col(column)
                .null_count()
                .alias(column)
                for column in columns
            ]
        )
        .collect()
    )

    for column in columns:

        count = null_counts[column][0]

        percentage = (
            count / total_rows * 100
            if total_rows > 0
            else 0
        )

        print(
            f"{column:<25}: "
            f"{count:>10,} "
            f"({percentage:.6f}%)"
        )

    # --------------------------------------------------
    # Blank strings
    # --------------------------------------------------

    text_columns = [
        "Account",
        "Account_duplicated_0",
        "Receiving Currency",
        "Payment Currency",
        "Payment Format",
    ]

    print("\n--- BLANK STRING CHECK ---")

    blank_counts = (
        lf.select(
            [
                (
                    pl.col(column)
                    .cast(pl.Utf8)
                    .str.strip_chars()
                    .eq("")
                    .fill_null(False)
                    .sum()
                    .alias(column)
                )
                for column in text_columns
            ]
        )
        .collect()
    )

    for column in text_columns:

        count = blank_counts[column][0]

        print(
            f"{column:<25}: "
            f"{count:,}"
        )

    # --------------------------------------------------
    # Label validation
    # --------------------------------------------------

    print("\n--- LABEL VALIDATION ---")

    invalid_labels = (
        lf.select(
            (
                ~pl.col("Is Laundering")
                .is_in([0, 1])
            )
            .sum()
            .alias("invalid_labels")
        )
        .collect()
        .item()
    )

    print(
        f"Invalid labels: "
        f"{invalid_labels:,}"
    )

    # --------------------------------------------------
    # Amount validation
    # --------------------------------------------------

    print("\n--- AMOUNT VALIDATION ---")

    amount_checks = (
        lf.select(
            [
                (
                    pl.col("Amount Paid") < 0
                )
                .sum()
                .alias("negative_amount_paid"),

                (
                    pl.col("Amount Received") < 0
                )
                .sum()
                .alias("negative_amount_received"),

                (
                    pl.col("Amount Paid") == 0
                )
                .sum()
                .alias("zero_amount_paid"),

                (
                    pl.col("Amount Received") == 0
                )
                .sum()
                .alias("zero_amount_received"),
            ]
        )
        .collect()
    )

    print(
        "Negative Amount Paid     :",
        f"{amount_checks['negative_amount_paid'][0]:,}",
    )

    print(
        "Negative Amount Received :",
        f"{amount_checks['negative_amount_received'][0]:,}",
    )

    print(
        "Zero Amount Paid         :",
        f"{amount_checks['zero_amount_paid'][0]:,}",
    )

    print(
        "Zero Amount Received     :",
        f"{amount_checks['zero_amount_received'][0]:,}",
    )

    # --------------------------------------------------
    # Critical identifier checks
    # --------------------------------------------------

    print("\n--- CRITICAL FIELD CHECK ---")

    critical_columns = [
        "Timestamp",
        "From Bank",
        "Account",
        "To Bank",
        "Account_duplicated_0",
        "Is Laundering",
    ]

    critical_nulls = (
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

        count = critical_nulls[column][0]

        status = (
            "PASS"
            if count == 0
            else "WARNING"
        )

        print(
            f"{column:<25}: "
            f"{count:>8,} "
            f"[{status}]"
        )

    # --------------------------------------------------
    # Summary
    # --------------------------------------------------

    print("\n" + "=" * 70)
    print("DATA QUALITY CHECK COMPLETE")
    print("=" * 70)

    print(
        "\nNOTE: No rows were changed or deleted."
    )


if __name__ == "__main__":
    main()