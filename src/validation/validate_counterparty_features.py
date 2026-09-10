from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v4_counterparty.parquet"
)


def main():

    print("=" * 80)
    print("GraphShield AML - Counterparty Feature Validation")
    print("=" * 80)

    lf = pl.scan_parquet(PATH)

    checks = (
        lf.select(
            [
                (
                    pl.col("sender_unique_receivers_1h")
                    > pl.col("sender_tx_count_1h")
                )
                .sum()
                .alias("sender_unique_gt_tx_1h"),

                (
                    pl.col("sender_unique_receivers_24h")
                    > pl.col("sender_tx_count_24h")
                )
                .sum()
                .alias("sender_unique_gt_tx_24h"),

                (
                    pl.col("receiver_unique_senders_1h")
                    > pl.col("receiver_tx_count_1h")
                )
                .sum()
                .alias("receiver_unique_gt_tx_1h"),

                (
                    pl.col("receiver_unique_senders_24h")
                    > pl.col("receiver_tx_count_24h")
                )
                .sum()
                .alias("receiver_unique_gt_tx_24h"),

                (
                    (pl.col("sender_fanout_ratio_1h") < 0)
                    | (pl.col("sender_fanout_ratio_1h") > 1)
                )
                .sum()
                .alias("invalid_sender_ratio"),

                (
                    (pl.col("receiver_fanin_ratio_1h") < 0)
                    | (pl.col("receiver_fanin_ratio_1h") > 1)
                )
                .sum()
                .alias("invalid_receiver_ratio"),
            ]
        )
        .collect()
    )

    print("\n--- LOGICAL CHECKS ---")
    print(checks)

    print("\n--- NEW COUNTERPARTY COUNTS ---")

    print(
        lf.select(
            [
                pl.col("new_receiver_for_sender")
                .sum()
                .alias("new_receiver_events"),

                pl.col("new_sender_for_receiver")
                .sum()
                .alias("new_sender_events"),
            ]
        )
        .collect()
    )


if __name__ == "__main__":
    main()