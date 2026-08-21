from pathlib import Path

import polars as pl

from schema import CANONICAL_COLUMNS, COLUMN_MAPPING


# ==========================================================
# Project paths
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "LI-Small_Trans.csv"
)

SILVER_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "silver"
)

SILVER_PATH = (
    SILVER_DIR
    / "transactions.parquet"
)


def main():

    print("=" * 70)
    print("GraphShield AML - Build Silver Canonical Dataset")
    print("=" * 70)

    # ======================================================
    # 1. Check raw dataset
    # ======================================================

    if not RAW_PATH.exists():
        print("\nERROR: Raw dataset not found.")
        print(RAW_PATH)
        return

    print("\nRaw dataset:")
    print(RAW_PATH)

    SILVER_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # ======================================================
    # 2. Scan raw CSV lazily
    # ======================================================

    print("\nScanning raw dataset...")

    lf = pl.scan_csv(RAW_PATH)

    # ======================================================
    # 3. Add source row number
    # ======================================================

    lf = lf.with_row_index(
        name="source_row_number",
        offset=0,
    )

    # ======================================================
    # 4. Rename raw columns
    # ======================================================

    lf = lf.rename(
        COLUMN_MAPPING
    )

    # ======================================================
    # 5. Canonical transformations
    # ======================================================

    lf = lf.with_columns(

        # ----------------------------------------------
        # Timestamp
        # ----------------------------------------------

        pl.col("event_ts")
        .str.to_datetime(
            strict=False
        )
        .alias("event_ts"),

        # ----------------------------------------------
        # Identifiers
        # ----------------------------------------------

        pl.col("from_bank")
        .cast(pl.String)
        .str.strip_chars()
        .alias("from_bank"),

        pl.col("from_account")
        .cast(pl.String)
        .str.strip_chars()
        .alias("from_account"),

        pl.col("to_bank")
        .cast(pl.String)
        .str.strip_chars()
        .alias("to_bank"),

        pl.col("to_account")
        .cast(pl.String)
        .str.strip_chars()
        .alias("to_account"),

        # ----------------------------------------------
        # Amount fields
        # ----------------------------------------------

        pl.col("amount_received")
        .cast(pl.Float64)
        .alias("amount_received"),

        pl.col("amount_paid")
        .cast(pl.Float64)
        .alias("amount_paid"),

        # ----------------------------------------------
        # Categorical fields
        # ----------------------------------------------

        pl.col("receiving_currency")
        .cast(pl.String)
        .str.strip_chars()
        .alias("receiving_currency"),

        pl.col("payment_currency")
        .cast(pl.String)
        .str.strip_chars()
        .alias("payment_currency"),

        pl.col("payment_format")
        .cast(pl.String)
        .str.strip_chars()
        .alias("payment_format"),

        # ----------------------------------------------
        # Target
        # ----------------------------------------------

        pl.col("is_laundering")
        .cast(pl.UInt8)
        .alias("is_laundering"),
    )

    # ======================================================
    # 6. Add lineage fields
    # ======================================================

    lf = lf.with_columns(

        pl.concat_str(
            [
                pl.lit("IBM_LI_SMALL_"),

                pl.col("source_row_number")
                .cast(pl.String),
            ]
        )
        .alias("transaction_id"),

        pl.lit(
            "IBM_LI_SMALL"
        )
        .alias("source_dataset"),
    )

    # ======================================================
    # 7. Select canonical column order
    # ======================================================

    lf = lf.select(
        CANONICAL_COLUMNS
    )

    # ======================================================
    # 8. Check transformation schema
    # ======================================================

    print("\n--- CANONICAL SCHEMA ---")

    schema = lf.collect_schema()

    for column in schema.names():

        print(
            f"{column:<25} "
            f"{schema[column]}"
        )

    # ======================================================
    # 9. Check timestamp parsing before writing
    # ======================================================

    print("\nChecking timestamp parsing...")

    timestamp_check = (
        lf.select(
            [
                pl.len()
                .alias("rows"),

                pl.col("event_ts")
                .null_count()
                .alias("null_event_ts"),
            ]
        )
        .collect()
    )

    total_rows = timestamp_check["rows"][0]
    timestamp_nulls = timestamp_check["null_event_ts"][0]

    print(
        f"Rows              : {total_rows:,}"
    )

    print(
        f"Null timestamps   : {timestamp_nulls:,}"
    )

    if timestamp_nulls > 0:

        print("\nWARNING:")
        print(
            "Some timestamps could not be parsed."
        )

        print(
            "Do not continue until they are investigated."
        )

        return

    # ======================================================
    # 10. Write Silver Parquet
    # ======================================================

    print("\nWriting Silver Parquet dataset...")

    lf.sink_parquet(
        SILVER_PATH,
        compression="zstd",
    )

    # ======================================================
    # Complete
    # ======================================================

    print("\nSilver dataset created successfully.")

    print("\nOutput:")
    print(SILVER_PATH)

    print("\n" + "=" * 70)
    print("SILVER BUILD COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()