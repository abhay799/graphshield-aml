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

    print("=" * 75)
    print("GraphShield AML - Initial AML Exploratory Data Analysis")
    print("=" * 75)

    if not DATA_PATH.exists():
        print("\nERROR: Dataset not found.")
        print(DATA_PATH)
        return

    print("\nScanning dataset...")

    lf = pl.scan_csv(DATA_PATH)

    # ==================================================
    # 1. Overall laundering rate
    # ==================================================

    print("\n--- 1. OVERALL LAUNDERING RATE ---")

    overall = (
        lf.select(
            [
                pl.len().alias("transactions"),
                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),
                (
                    pl.col("Is Laundering").mean()
                    * 100
                ).alias("laundering_rate_percent"),
            ]
        )
        .collect()
    )

    print(overall)

    # ==================================================
    # 2. Laundering by payment format
    # ==================================================

    print("\n--- 2. LAUNDERING BY PAYMENT FORMAT ---")

    payment_format = (
        lf.group_by("Payment Format")
        .agg(
            [
                pl.len().alias("transactions"),

                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),
            ]
        )
        .with_columns(
            (
                pl.col("laundering_transactions")
                / pl.col("transactions")
                * 100
            ).alias("laundering_rate_percent")
        )
        .sort(
            "laundering_rate_percent",
            descending=True
        )
        .collect()
    )

    print(payment_format)

    # ==================================================
    # 3. Laundering by payment currency
    # ==================================================

    print("\n--- 3. LAUNDERING BY PAYMENT CURRENCY ---")

    payment_currency = (
        lf.group_by("Payment Currency")
        .agg(
            [
                pl.len().alias("transactions"),

                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),
            ]
        )
        .with_columns(
            (
                pl.col("laundering_transactions")
                / pl.col("transactions")
                * 100
            ).alias("laundering_rate_percent")
        )
        .sort(
            "transactions",
            descending=True
        )
        .collect()
    )

    print(payment_currency)

    # ==================================================
    # 4. Laundering by receiving currency
    # ==================================================

    print("\n--- 4. LAUNDERING BY RECEIVING CURRENCY ---")

    receiving_currency = (
        lf.group_by("Receiving Currency")
        .agg(
            [
                pl.len().alias("transactions"),

                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),
            ]
        )
        .with_columns(
            (
                pl.col("laundering_transactions")
                / pl.col("transactions")
                * 100
            ).alias("laundering_rate_percent")
        )
        .sort(
            "transactions",
            descending=True
        )
        .collect()
    )

    print(receiving_currency)

    # ==================================================
    # 5. Laundering by sender bank
    # ==================================================

    print("\n--- 5. TOP SENDER BANKS BY LAUNDERING TRANSACTIONS ---")

    sender_banks = (
        lf.group_by("From Bank")
        .agg(
            [
                pl.len().alias("transactions"),

                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),
            ]
        )
        .with_columns(
            (
                pl.col("laundering_transactions")
                / pl.col("transactions")
                * 100
            ).alias("laundering_rate_percent")
        )
        .filter(
            pl.col("transactions") >= 100
        )
        .sort(
            "laundering_transactions",
            descending=True
        )
        .head(20)
        .collect()
    )

    print(sender_banks)

    # ==================================================
    # 6. Laundering by receiving bank
    # ==================================================

    print("\n--- 6. TOP RECEIVING BANKS BY LAUNDERING TRANSACTIONS ---")

    receiver_banks = (
        lf.group_by("To Bank")
        .agg(
            [
                pl.len().alias("transactions"),

                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),
            ]
        )
        .with_columns(
            (
                pl.col("laundering_transactions")
                / pl.col("transactions")
                * 100
            ).alias("laundering_rate_percent")
        )
        .filter(
            pl.col("transactions") >= 100
        )
        .sort(
            "laundering_transactions",
            descending=True
        )
        .head(20)
        .collect()
    )

    print(receiver_banks)

    # ==================================================
    # 7. Amount comparison
    # ==================================================

    print("\n--- 7. AMOUNT PAID: LEGITIMATE VS LAUNDERING ---")

    amount_comparison = (
        lf.group_by("Is Laundering")
        .agg(
            [
                pl.len().alias("transactions"),

                pl.col("Amount Paid")
                .mean()
                .alias("mean_amount"),

                pl.col("Amount Paid")
                .median()
                .alias("median_amount"),

                pl.col("Amount Paid")
                .quantile(0.90)
                .alias("p90_amount"),

                pl.col("Amount Paid")
                .quantile(0.99)
                .alias("p99_amount"),
            ]
        )
        .sort("Is Laundering")
        .collect()
    )

    print(amount_comparison)

    print("\n" + "=" * 75)
    print("INITIAL AML EDA COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    main()