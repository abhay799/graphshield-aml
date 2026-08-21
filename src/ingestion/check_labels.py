from pathlib import Path

import polars as pl


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "LI-Small_Trans.csv"


def main():
    print("=" * 60)
    print("GraphShield AML - Label Inspection")
    print("=" * 60)

    # Check file
    if not DATA_PATH.exists():
        print("\nERROR: Dataset file was not found.")
        return

    print("\nLoading dataset...")

    df = pl.read_csv(DATA_PATH)

    print("\n--- Available Columns ---")

    for column in df.columns:
        print(column)

    # IBM AML dataset label column
    label_column = "Is Laundering"

    # Safety check
    if label_column not in df.columns:
        print(f"\nERROR: '{label_column}' column not found.")
        print("Available columns:")
        print(df.columns)
        return

    print(f"\n--- Label Column: {label_column} ---")

    # Count each class
    label_counts = (
        df
        .group_by(label_column)
        .len()
        .sort(label_column)
    )

    print(label_counts)

    print("\n--- Label Distribution ---")

    total_rows = df.height

    for row in label_counts.iter_rows(named=True):
        label = row[label_column]
        count = row["len"]
        percentage = (count / total_rows) * 100

        print(
            f"Label {label}: "
            f"{count:,} rows "
            f"({percentage:.6f}%)"
        )

    print("\n--- Dataset Summary ---")
    print(f"Total transactions : {total_rows:,}")
    print(
        f"Total laundering   : "
        f"{df.filter(pl.col(label_column) == 1).height:,}"
    )
    print(
        f"Total legitimate   : "
        f"{df.filter(pl.col(label_column) == 0).height:,}"
    )

    print("\n--- Done ---")


if __name__ == "__main__":
    main()