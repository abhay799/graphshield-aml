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
    print("GraphShield AML - Timestamp Inspection")
    print("=" * 70)

    if not DATA_PATH.exists():
        print("\nERROR: Dataset not found.")
        return

    print("\nLoading timestamps...")

    df = pl.read_csv(
        DATA_PATH,
        columns=["Timestamp"],
    )

    print("\n--- RAW TIMESTAMP SAMPLE ---")

    print(
        df["Timestamp"]
        .head(10)
    )

    print(
        "\nOriginal datatype:",
        df.schema["Timestamp"],
    )

    # --------------------------------------------
    # Parse timestamp
    # --------------------------------------------

    parsed = df.with_columns(

        pl.col("Timestamp")
        .str.to_datetime(
            strict=False
        )
        .alias("parsed_timestamp")

    )

    # --------------------------------------------
    # Parse failures
    # --------------------------------------------

    parse_failures = (
        parsed
        .filter(
            pl.col("parsed_timestamp")
            .is_null()
        )
        .height
    )

    print("\n--- PARSING ---")

    print(
        f"Timestamp parse failures: "
        f"{parse_failures:,}"
    )

    # --------------------------------------------
    # Date range
    # --------------------------------------------

    valid = parsed.filter(
        pl.col("parsed_timestamp")
        .is_not_null()
    )

    minimum = valid[
        "parsed_timestamp"
    ].min()

    maximum = valid[
        "parsed_timestamp"
    ].max()

    print("\n--- TIME RANGE ---")

    print(f"Earliest transaction : {minimum}")
    print(f"Latest transaction   : {maximum}")

    # --------------------------------------------
    # Unique days
    # --------------------------------------------

    unique_days = (
        valid.select(
            pl.col("parsed_timestamp")
            .dt.date()
            .n_unique()
        )
        .item()
    )

    print(
        f"Unique transaction days: "
        f"{unique_days:,}"
    )

    # --------------------------------------------
    # Transactions by hour
    # --------------------------------------------

    print("\n--- TRANSACTIONS BY HOUR ---")

    hourly = (
        valid
        .with_columns(
            pl.col("parsed_timestamp")
            .dt.hour()
            .alias("hour")
        )
        .group_by("hour")
        .len()
        .sort("hour")
    )

    print(hourly)

    print("\n--- Done ---")


if __name__ == "__main__":
    main()