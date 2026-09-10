from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v2_history.parquet"
)


def main():

    print("=" * 78)
    print("GraphShield AML - Historical Feature Validation")
    print("=" * 78)

    if not FEATURE_PATH.exists():

        print("\nERROR: Historical feature dataset missing.")
        return

    lf = pl.scan_parquet(
        FEATURE_PATH
    )

    # ------------------------------------------------------
    # Row count
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # Prior count ranges
    # ------------------------------------------------------

    print("\n--- PRIOR COUNT RANGES ---")

    ranges = (
        lf.select(
            [
                pl.col(
                    "sender_prior_tx_count"
                )
                .min()
                .alias("sender_min"),

                pl.col(
                    "sender_prior_tx_count"
                )
                .max()
                .alias("sender_max"),

                pl.col(
                    "receiver_prior_tx_count"
                )
                .min()
                .alias("receiver_min"),

                pl.col(
                    "receiver_prior_tx_count"
                )
                .max()
                .alias("receiver_max"),
            ]
        )
        .collect()
    )

    print(ranges)

    # ------------------------------------------------------
    # Negative checks
    # ------------------------------------------------------

    print("\n--- NEGATIVE VALUE CHECK ---")

    negative = (
        lf.select(
            [
                (
                    pl.col(
                        "sender_prior_tx_count"
                    ) < 0
                )
                .sum()
                .alias("negative_sender_count"),

                (
                    pl.col(
                        "receiver_prior_tx_count"
                    ) < 0
                )
                .sum()
                .alias("negative_receiver_count"),

                (
                    pl.col(
                        "sender_seconds_since_previous"
                    ) < 0
                )
                .sum()
                .alias("negative_sender_time"),

                (
                    pl.col(
                        "receiver_seconds_since_previous"
                    ) < 0
                )
                .sum()
                .alias("negative_receiver_time"),
            ]
        )
        .collect()
    )

    print(negative)

    # ------------------------------------------------------
    # First transaction statistics
    # ------------------------------------------------------

    print("\n--- FIRST-TIME ACCOUNT ACTIVITY ---")

    first_time = (
        lf.select(
            [
                (
                    pl.col(
                        "sender_prior_tx_count"
                    ) == 0
                )
                .sum()
                .alias("first_time_senders"),

                (
                    pl.col(
                        "receiver_prior_tx_count"
                    ) == 0
                )
                .sum()
                .alias("first_time_receivers"),
            ]
        )
        .collect()
    )

    print(first_time)

    # ------------------------------------------------------
    # Same timestamp leakage check
    # ------------------------------------------------------

    print("\n--- SAME-TIMESTAMP CONSISTENCY ---")

    sender_violations = (
        lf.group_by(
            [
                "from_account_key",
                "event_ts",
            ]
        )
        .agg(
            pl.col(
                "sender_prior_tx_count"
            )
            .n_unique()
            .alias("unique_prior_counts")
        )
        .filter(
            pl.col("unique_prior_counts") > 1
        )
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    receiver_violations = (
        lf.group_by(
            [
                "to_account_key",
                "event_ts",
            ]
        )
        .agg(
            pl.col(
                "receiver_prior_tx_count"
            )
            .n_unique()
            .alias("unique_prior_counts")
        )
        .filter(
            pl.col("unique_prior_counts") > 1
        )
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    print(
        "Sender same-timestamp violations:",
        sender_violations
    )

    print(
        "Receiver same-timestamp violations:",
        receiver_violations
    )

    # ------------------------------------------------------
    # Example rows
    # ------------------------------------------------------

    print("\n--- SAMPLE HISTORICAL FEATURES ---")

    sample = (
        lf.select(
            [
                "transaction_id",
                "event_ts",
                "from_account_key",

                "amount_paid",

                "sender_prior_tx_count",
                "sender_prior_amount_sum",
                "sender_prior_amount_avg",
                "sender_seconds_since_previous",

                "receiver_prior_tx_count",

                "is_laundering",
            ]
        )
        .head(20)
        .collect()
    )

    print(sample)

    print("\n" + "=" * 78)
    print("HISTORICAL FEATURE VALIDATION COMPLETE")
    print("=" * 78)


if __name__ == "__main__":
    main()