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
    print("GraphShield AML - Bank Flow Analysis")
    print("=" * 70)

    lf = (
        pl.scan_csv(DATA_PATH)
        .with_columns(
            (
                pl.col("From Bank")
                != pl.col("To Bank")
            )
            .alias("is_cross_bank")
        )
    )

    print("\n--- SAME BANK VS CROSS BANK ---")

    results = (
        lf.group_by("is_cross_bank")
        .agg(
            [
                pl.len().alias("transactions"),

                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),

                pl.col("Amount Paid")
                .median()
                .alias("median_amount"),

                pl.col("Amount Paid")
                .mean()
                .alias("mean_amount"),
            ]
        )
        .with_columns(
            (
                pl.col("laundering_transactions")
                / pl.col("transactions")
                * 100
            ).alias("laundering_rate_percent")
        )
        .sort("is_cross_bank")
        .collect()
    )

    print(results)

    print("\nInterpretation:")
    print("False = sender and receiver use the same bank.")
    print("True  = funds move between different banks.")


if __name__ == "__main__":
    main()