from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "LI-Small_Trans.csv"


def main():

    print("=" * 60)
    print("GraphShield AML - Duplicate Analysis")
    print("=" * 60)

    print("\nLoading dataset...")

    df = pl.read_csv(DATA_PATH)

    total_rows = df.height

    print(f"\nTotal rows: {total_rows:,}")

    # Number of unique complete rows
    unique_rows = df.unique().height

    duplicate_rows = total_rows - unique_rows

    duplicate_percentage = (
        duplicate_rows / total_rows * 100
        if total_rows > 0
        else 0
    )

    print("\n--- COMPLETE ROW DUPLICATES ---")

    print(f"Unique rows       : {unique_rows:,}")
    print(f"Duplicate rows    : {duplicate_rows:,}")
    print(f"Duplicate percent : {duplicate_percentage:.6f}%")

    print("\nIMPORTANT:")
    print(
        "Do not delete duplicate-looking transactions yet. "
        "We first need to determine whether they represent "
        "data duplication or legitimate repeated transactions."
    )

    print("\n--- Done ---")


if __name__ == "__main__":
    main()