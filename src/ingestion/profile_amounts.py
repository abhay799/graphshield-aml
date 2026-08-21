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
    print("GraphShield AML - Amount & Statistical Profiling")
    print("=" * 70)

    # --------------------------------------------------
    # Check dataset
    # --------------------------------------------------

    if not DATA_PATH.exists():
        print("\nERROR: Dataset not found.")
        print(DATA_PATH)
        return

    print("\nDataset:")
    print(DATA_PATH)

    # --------------------------------------------------
    # Lazy scan
    # --------------------------------------------------

    print("\nScanning dataset...")

    lf = pl.scan_csv(DATA_PATH)

    # --------------------------------------------------
    # Basic statistics
    # --------------------------------------------------

    print("\n--- AMOUNT PAID STATISTICS ---")

    paid_stats = (
        lf.select(
            [
                pl.col("Amount Paid").min().alias("min"),
                pl.col("Amount Paid").max().alias("max"),
                pl.col("Amount Paid").mean().alias("mean"),
                pl.col("Amount Paid").median().alias("median"),
                pl.col("Amount Paid").std().alias("std"),
                pl.col("Amount Paid")
                .quantile(0.25)
                .alias("q25"),
                pl.col("Amount Paid")
                .quantile(0.75)
                .alias("q75"),
                pl.col("Amount Paid")
                .quantile(0.90)
                .alias("q90"),
                pl.col("Amount Paid")
                .quantile(0.95)
                .alias("q95"),
                pl.col("Amount Paid")
                .quantile(0.99)
                .alias("q99"),
                pl.col("Amount Paid")
                .quantile(0.999)
                .alias("q999"),
            ]
        )
        .collect()
    )

    print(paid_stats)

    print("\n--- AMOUNT RECEIVED STATISTICS ---")

    received_stats = (
        lf.select(
            [
                pl.col("Amount Received").min().alias("min"),
                pl.col("Amount Received").max().alias("max"),
                pl.col("Amount Received").mean().alias("mean"),
                pl.col("Amount Received").median().alias("median"),
                pl.col("Amount Received").std().alias("std"),
                pl.col("Amount Received")
                .quantile(0.25)
                .alias("q25"),
                pl.col("Amount Received")
                .quantile(0.75)
                .alias("q75"),
                pl.col("Amount Received")
                .quantile(0.90)
                .alias("q90"),
                pl.col("Amount Received")
                .quantile(0.95)
                .alias("q95"),
                pl.col("Amount Received")
                .quantile(0.99)
                .alias("q99"),
                pl.col("Amount Received")
                .quantile(0.999)
                .alias("q999"),
            ]
        )
        .collect()
    )

    print(received_stats)

    print("\n--- Done ---")


if __name__ == "__main__":
    main()