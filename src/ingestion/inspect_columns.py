from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "LI-Small_Trans.csv"


def main():
    print("=" * 70)
    print("GraphShield AML - Column Understanding")
    print("=" * 70)

    print("\nLoading sample data...")

    # Read only a small sample.
    # We are understanding the columns, not doing full EDA yet.
    df = pl.read_csv(DATA_PATH, n_rows=100)

    print("\n--- DATASET COLUMNS ---")

    for i, column in enumerate(df.columns, start=1):
        print(f"{i}. {column}")

    print("\n" + "=" * 70)
    print("COLUMN-BY-COLUMN INSPECTION")
    print("=" * 70)

    for column in df.columns:

        print(f"\nCOLUMN: {column}")
        print(f"Data type: {df.schema[column]}")

        # Number of unique values in sample
        unique_count = df[column].n_unique()

        print(f"Unique values in sample: {unique_count}")

        # Show sample values
        print("Sample values:")

        values = (
            df[column]
            .drop_nulls()
            .unique()
            .head(10)
            .to_list()
        )

        for value in values:
            print(f"  - {value}")

        print("-" * 70)

    print("\n--- FIRST 5 COMPLETE TRANSACTIONS ---")

    print(df.head(5))

    print("\n--- Done ---")


if __name__ == "__main__":
    main()