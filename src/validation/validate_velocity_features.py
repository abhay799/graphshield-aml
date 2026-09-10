from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v3_velocity.parquet"
)


def main():

    print("=" * 80)
    print("GraphShield AML - Velocity Feature Validation")
    print("=" * 80)

    if not FEATURE_PATH.exists():

        print("\nERROR: Velocity dataset not found.")
        return

    lf = pl.scan_parquet(
        FEATURE_PATH
    )

    # ======================================================
    # Row count
    # ======================================================

    rows = (
        lf.select(
            pl.len()
        )
        .collect()
        .item()
    )

    print("\n--- ROW COUNT ---")

    print(
        f"Rows: {rows:,}"
    )

    # ======================================================
    # Velocity columns
    # ======================================================

    velocity_columns = [
        "sender_tx_count_1h",
        "sender_tx_count_24h",
        "sender_tx_count_7d",

        "sender_amount_sum_1h",
        "sender_amount_sum_24h",
        "sender_amount_sum_7d",

        "receiver_tx_count_1h",
        "receiver_tx_count_24h",
        "receiver_tx_count_7d",

        "receiver_amount_sum_1h",
        "receiver_amount_sum_24h",
        "receiver_amount_sum_7d",
    ]

    # ======================================================
    # Null check
    # ======================================================

    print("\n--- NULL CHECK ---")

    nulls = (
        lf.select(
            [
                pl.col(column)
                .null_count()
                .alias(column)

                for column
                in velocity_columns
            ]
        )
        .collect()
    )

    for column in velocity_columns:

        count = nulls[column][0]

        status = (
            "PASS"
            if count == 0
            else "FAIL"
        )

        print(
            f"{column:<35}"
            f"{count:>10,} "
            f"[{status}]"
        )

    # ======================================================
    # Negative checks
    # ======================================================

    print("\n--- NEGATIVE VALUE CHECK ---")

    negatives = (
        lf.select(
            [
                (
                    pl.col(column) < 0
                )
                .sum()
                .alias(column)

                for column
                in velocity_columns
            ]
        )
        .collect()
    )

    for column in velocity_columns:

        count = negatives[column][0]

        status = (
            "PASS"
            if count == 0
            else "FAIL"
        )

        print(
            f"{column:<35}"
            f"{count:>10,} "
            f"[{status}]"
        )

    # ======================================================
    # Window ordering
    # ======================================================

    print("\n--- WINDOW CONSISTENCY ---")

    ordering = (
        lf.select(
            [
                (
                    pl.col("sender_tx_count_1h")
                    > pl.col("sender_tx_count_24h")
                )
                .sum()
                .alias(
                    "sender_1h_gt_24h"
                ),

                (
                    pl.col("sender_tx_count_24h")
                    > pl.col("sender_tx_count_7d")
                )
                .sum()
                .alias(
                    "sender_24h_gt_7d"
                ),

                (
                    pl.col("receiver_tx_count_1h")
                    > pl.col("receiver_tx_count_24h")
                )
                .sum()
                .alias(
                    "receiver_1h_gt_24h"
                ),

                (
                    pl.col("receiver_tx_count_24h")
                    > pl.col("receiver_tx_count_7d")
                )
                .sum()
                .alias(
                    "receiver_24h_gt_7d"
                ),
            ]
        )
        .collect()
    )

    print(ordering)

    # ======================================================
    # Amount window consistency
    # ======================================================

    print("\n--- AMOUNT WINDOW CONSISTENCY ---")

    amount_ordering = (
        lf.select(
            [
                (
                    pl.col("sender_amount_sum_1h")
                    > pl.col("sender_amount_sum_24h")
                )
                .sum()
                .alias(
                    "sender_amount_1h_gt_24h"
                ),

                (
                    pl.col("sender_amount_sum_24h")
                    > pl.col("sender_amount_sum_7d")
                )
                .sum()
                .alias(
                    "sender_amount_24h_gt_7d"
                ),

                (
                    pl.col("receiver_amount_sum_1h")
                    > pl.col("receiver_amount_sum_24h")
                )
                .sum()
                .alias(
                    "receiver_amount_1h_gt_24h"
                ),

                (
                    pl.col("receiver_amount_sum_24h")
                    > pl.col("receiver_amount_sum_7d")
                )
                .sum()
                .alias(
                    "receiver_amount_24h_gt_7d"
                ),
            ]
        )
        .collect()
    )

    print(amount_ordering)

    # ======================================================
    # Same timestamp consistency
    # ======================================================

    print("\n--- SAME-TIMESTAMP CONSISTENCY ---")

    sender_same_ts = (
        lf.group_by(
            [
                "from_account_key",
                "event_ts",
            ]
        )
        .agg(
            [
                pl.col("sender_tx_count_1h")
                .n_unique()
                .alias("n1"),

                pl.col("sender_tx_count_24h")
                .n_unique()
                .alias("n24"),

                pl.col("sender_tx_count_7d")
                .n_unique()
                .alias("n7"),
            ]
        )
        .filter(
            (pl.col("n1") > 1)
            | (pl.col("n24") > 1)
            | (pl.col("n7") > 1)
        )
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    print(
        "Sender same-timestamp violations:",
        sender_same_ts
    )

    receiver_same_ts = (
        lf.group_by(
            [
                "to_account_key",
                "event_ts",
            ]
        )
        .agg(
            [
                pl.col("receiver_tx_count_1h")
                .n_unique()
                .alias("n1"),

                pl.col("receiver_tx_count_24h")
                .n_unique()
                .alias("n24"),

                pl.col("receiver_tx_count_7d")
                .n_unique()
                .alias("n7"),
            ]
        )
        .filter(
            (pl.col("n1") > 1)
            | (pl.col("n24") > 1)
            | (pl.col("n7") > 1)
        )
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    print(
        "Receiver same-timestamp violations:",
        receiver_same_ts
    )

    # ======================================================
    # Feature ranges
    # ======================================================

    print("\n--- VELOCITY RANGES ---")

    ranges = (
        lf.select(
            [
                pl.col("sender_tx_count_1h")
                .max()
                .alias("max_sender_1h"),

                pl.col("sender_tx_count_24h")
                .max()
                .alias("max_sender_24h"),

                pl.col("sender_tx_count_7d")
                .max()
                .alias("max_sender_7d"),

                pl.col("receiver_tx_count_1h")
                .max()
                .alias("max_receiver_1h"),

                pl.col("receiver_tx_count_24h")
                .max()
                .alias("max_receiver_24h"),

                pl.col("receiver_tx_count_7d")
                .max()
                .alias("max_receiver_7d"),
            ]
        )
        .collect()
    )

    print(ranges)

    # ======================================================
    # Preview highest velocity
    # ======================================================

    print("\n--- HIGH-VELOCITY TRANSACTION EXAMPLES ---")

    examples = (
        lf.select(
            [
                "transaction_id",
                "event_ts",
                "from_account_key",
                "to_account_key",
                "amount_paid",

                "sender_tx_count_1h",
                "sender_tx_count_24h",

                "receiver_tx_count_1h",
                "receiver_tx_count_24h",

                "payment_format",
                "is_laundering",
            ]
        )
        .sort(
            "sender_tx_count_1h",
            descending=True
        )
        .head(20)
        .collect()
    )

    print(examples)

    print("\n" + "=" * 80)
    print("VELOCITY VALIDATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()