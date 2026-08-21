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
    print("GraphShield AML - Currency Flow Analysis")
    print("=" * 70)

    lf = (
        pl.scan_csv(DATA_PATH)
        .with_columns(
            (
                pl.col("Payment Currency")
                != pl.col("Receiving Currency")
            )
            .alias("is_cross_currency")
        )
    )

    results = (
        lf.group_by("is_cross_currency")
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
        .sort("is_cross_currency")
        .collect()
    )

    print("\n--- SAME VS CROSS CURRENCY ---")

    print(results)

    print("\nInterpretation:")
    print("False = payment and receiving currency are the same.")
    print("True  = currency changes during the transaction.")


if __name__ == "__main__":
    main()