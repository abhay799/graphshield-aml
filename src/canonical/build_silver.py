from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "LI-Small_Trans.csv"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "silver"
    / "transactions.parquet"
)


def main():

    print("=" * 80)
    print("GraphShield AML - Canonical Silver Transaction Build")
    print("=" * 80)

    # ======================================================
    # Input validation
    # ======================================================

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Raw dataset not found:\n{INPUT_PATH}"
        )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\nInput:")
    print(INPUT_PATH)

    print("\nOutput:")
    print(OUTPUT_PATH)

    # ======================================================
    # Read immutable raw source
    # ======================================================

    print("\nReading raw CSV with Polars Lazy API...")

    raw = (
        pl.scan_csv(
            INPUT_PATH
        )
        .with_row_index(
            "source_row_number",
            offset=0,
        )
    )

    raw_schema = raw.collect_schema()

    print("\nRaw columns:")

    for column in raw_schema.names():
        print(f"  - {column}")

    # ======================================================
    # Required source columns
    # ======================================================

    required_raw_columns = [
        "Timestamp",
        "From Bank",
        "Account",
        "To Bank",
        "Account_duplicated_0",
        "Amount Received",
        "Receiving Currency",
        "Amount Paid",
        "Payment Currency",
        "Payment Format",
        "Is Laundering",
    ]

    missing_columns = [
        column
        for column in required_raw_columns
        if column not in raw_schema.names()
    ]

    if missing_columns:
        raise RuntimeError(
            "Missing required raw columns:\n"
            + "\n".join(
                f"  - {column}"
                for column in missing_columns
            )
        )

    # ======================================================
    # Build canonical Silver schema
    # ======================================================

    print("\nBuilding canonical transaction schema...")

    silver = (
        raw.select(
            [
                # Stable lineage-based ID
                pl.concat_str(
                    [
                        pl.lit("IBM_LI_SMALL_"),
                        pl.col(
                            "source_row_number"
                        ).cast(pl.String),
                    ]
                )
                .alias(
                    "transaction_id"
                ),

                # Explicit UTC interpretation of the
                # timezone-naive synthetic source timestamp
                pl.col("Timestamp")
                .str.strptime(
                    pl.Datetime,
                    strict=True,
                )
                .dt.replace_time_zone(
                    "UTC"
                )
                .alias(
                    "event_ts"
                ),

                pl.col("From Bank")
                .cast(pl.String)
                .alias(
                    "from_bank"
                ),

                pl.col("Account")
                .cast(pl.String)
                .alias(
                    "from_account"
                ),

                pl.col("To Bank")
                .cast(pl.String)
                .alias(
                    "to_bank"
                ),

                # IMPORTANT:
                # Polars renamed the second raw Account column
                # to Account_duplicated_0.
                pl.col(
                    "Account_duplicated_0"
                )
                .cast(pl.String)
                .alias(
                    "to_account"
                ),

                pl.col(
                    "Amount Received"
                )
                .cast(pl.Float64)
                .alias(
                    "amount_received"
                ),

                pl.col(
                    "Receiving Currency"
                )
                .cast(pl.String)
                .alias(
                    "receiving_currency"
                ),

                pl.col(
                    "Amount Paid"
                )
                .cast(pl.Float64)
                .alias(
                    "amount_paid"
                ),

                pl.col(
                    "Payment Currency"
                )
                .cast(pl.String)
                .alias(
                    "payment_currency"
                ),

                pl.col(
                    "Payment Format"
                )
                .cast(pl.String)
                .alias(
                    "payment_format"
                ),

                pl.col(
                    "Is Laundering"
                )
                .cast(pl.UInt8)
                .alias(
                    "is_laundering"
                ),

                pl.col(
                    "source_row_number"
                ),

                pl.lit(
                    "IBM_LI_SMALL"
                )
                .alias(
                    "source_dataset"
                ),
            ]
        )
    )

    # ======================================================
    # Schema check before writing
    # ======================================================

    print("\nOutput schema:")

    schema = silver.collect_schema()

    for name, dtype in schema.items():
        print(
            f"{name:<28} {dtype}"
        )

    # ======================================================
    # Write Silver
    # ======================================================

    print("\nWriting Silver Parquet...")

    silver.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    # ======================================================
    # Verify written artifact
    # ======================================================

    written = pl.scan_parquet(
        OUTPUT_PATH
    )

    summary = (
        written.select(
            [
                pl.len()
                .alias("rows"),

                pl.col(
                    "transaction_id"
                )
                .n_unique()
                .alias(
                    "unique_transaction_ids"
                ),

                pl.col(
                    "is_laundering"
                )
                .sum()
                .alias(
                    "positives"
                ),

                pl.col(
                    "event_ts"
                )
                .min()
                .alias(
                    "start"
                ),

                pl.col(
                    "event_ts"
                )
                .max()
                .alias(
                    "end"
                ),
            ]
        )
        .collect()
    )

    print("\n--- SILVER SUMMARY ---")
    print(summary)

    final_schema = (
        written.collect_schema()
    )

    print(
        "\nevent_ts dtype:",
        final_schema[
            "event_ts"
        ],
    )

    print("\nCreated:")
    print(OUTPUT_PATH)

    print("\n" + "=" * 80)
    print("SILVER BUILD COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()