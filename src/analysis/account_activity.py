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
    print("GraphShield AML - Account Activity Analysis")
    print("=" * 75)

    lf = pl.scan_csv(DATA_PATH)

    # ==================================================
    # Sender activity
    # ==================================================

    print("\n--- MOST ACTIVE SENDER ACCOUNTS ---")

    senders = (
        lf.group_by("Account")
        .agg(
            [
                pl.len()
                .alias("transactions_sent"),

                pl.col("Account_duplicated_0")
                .n_unique()
                .alias("unique_receivers"),

                pl.col("Amount Paid")
                .sum()
                .alias("total_amount_sent"),

                pl.col("Amount Paid")
                .mean()
                .alias("mean_amount_sent"),

                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),
            ]
        )
        .sort(
            "transactions_sent",
            descending=True
        )
        .head(20)
        .collect()
    )

    print(senders)

    # ==================================================
    # Receiver activity
    # ==================================================

    print("\n--- MOST ACTIVE RECEIVER ACCOUNTS ---")

    receivers = (
        lf.group_by("Account_duplicated_0")
        .agg(
            [
                pl.len()
                .alias("transactions_received"),

                pl.col("Account")
                .n_unique()
                .alias("unique_senders"),

                pl.col("Amount Received")
                .sum()
                .alias("total_amount_received"),

                pl.col("Amount Received")
                .mean()
                .alias("mean_amount_received"),

                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),
            ]
        )
        .sort(
            "transactions_received",
            descending=True
        )
        .head(20)
        .collect()
    )

    print(receivers)


if __name__ == "__main__":
    main()