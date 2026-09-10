from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v3_velocity.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v4_counterparty.parquet"
)


DEV_MODE = False
DEV_ROWS = 250_000


def sender_unique_window(
    sender_pairs: pl.LazyFrame,
    period: str,
    suffix: str,
) -> pl.LazyFrame:

    feature_name = f"sender_unique_receivers_{suffix}"

    rolling = (
        sender_pairs
        .rolling(
            index_column="event_ts",
            period=period,
            group_by="from_account_key",
            closed="left",
        )
        .agg(
            pl.col("to_account_key")
            .n_unique()
            .alias(feature_name)
        )
    )

    # Multiple counterparties may exist at the exact same timestamp.
    # Since the window excludes the current timestamp, they should all
    # have the same historical value.
    return (
        rolling
        .group_by(
            [
                "from_account_key",
                "event_ts",
            ]
        )
        .agg(
            pl.col(feature_name)
            .first()
            .alias(feature_name)
        )
    )


def receiver_unique_window(
    receiver_pairs: pl.LazyFrame,
    period: str,
    suffix: str,
) -> pl.LazyFrame:

    feature_name = f"receiver_unique_senders_{suffix}"

    rolling = (
        receiver_pairs
        .rolling(
            index_column="event_ts",
            period=period,
            group_by="to_account_key",
            closed="left",
        )
        .agg(
            pl.col("from_account_key")
            .n_unique()
            .alias(feature_name)
        )
    )

    return (
        rolling
        .group_by(
            [
                "to_account_key",
                "event_ts",
            ]
        )
        .agg(
            pl.col(feature_name)
            .first()
            .alias(feature_name)
        )
    )


def main():

    print("=" * 80)
    print("GraphShield AML - Counterparty / Fan-In / Fan-Out Features")
    print("=" * 80)

    if not INPUT_PATH.exists():
        print("\nERROR: V3 velocity dataset not found.")
        print(INPUT_PATH)
        return

    base = pl.scan_parquet(INPUT_PATH)

    if DEV_MODE:
        print(
            f"\nDEV MODE: using first {DEV_ROWS:,} transactions."
        )

        base = base.head(DEV_ROWS)

    else:
        print("\nFULL DATASET MODE.")

    # ======================================================
    # Unique directed account pairs
    # ======================================================

    print("\nPreparing sender-counterparty history...")

    sender_pairs = (
        base
        .select(
            [
                "from_account_key",
                "to_account_key",
                "event_ts",
            ]
        )
        .unique()
        .sort(
            [
                "from_account_key",
                "event_ts",
            ]
        )
    )

    print("Preparing receiver-counterparty history...")

    receiver_pairs = (
        base
        .select(
            [
                "to_account_key",
                "from_account_key",
                "event_ts",
            ]
        )
        .unique()
        .sort(
            [
                "to_account_key",
                "event_ts",
            ]
        )
    )

    # ======================================================
    # Rolling unique counterparties
    # ======================================================

    print("\nBuilding sender unique receivers...")

    sender_1h = sender_unique_window(
        sender_pairs,
        "1h",
        "1h",
    )

    sender_24h = sender_unique_window(
        sender_pairs,
        "24h",
        "24h",
    )

    sender_7d = sender_unique_window(
        sender_pairs,
        "7d",
        "7d",
    )

    print("Building receiver unique senders...")

    receiver_1h = receiver_unique_window(
        receiver_pairs,
        "1h",
        "1h",
    )

    receiver_24h = receiver_unique_window(
        receiver_pairs,
        "24h",
        "24h",
    )

    receiver_7d = receiver_unique_window(
        receiver_pairs,
        "7d",
        "7d",
    )

    # ======================================================
    # First-seen counterparty relationship
    # ======================================================

    print("\nCalculating first-seen counterparties...")

    sender_first_seen = (
        base
        .group_by(
            [
                "from_account_key",
                "to_account_key",
            ]
        )
        .agg(
            pl.col("event_ts")
            .min()
            .alias("sender_receiver_first_seen_ts")
        )
    )

    receiver_first_seen = (
        base
        .group_by(
            [
                "to_account_key",
                "from_account_key",
            ]
        )
        .agg(
            pl.col("event_ts")
            .min()
            .alias("receiver_sender_first_seen_ts")
        )
    )

    # ======================================================
    # Join
    # ======================================================

    print("Joining counterparty features...")

    features = (
        base
        .join(
            sender_1h,
            on=[
                "from_account_key",
                "event_ts",
            ],
            how="left",
        )
        .join(
            sender_24h,
            on=[
                "from_account_key",
                "event_ts",
            ],
            how="left",
        )
        .join(
            sender_7d,
            on=[
                "from_account_key",
                "event_ts",
            ],
            how="left",
        )
        .join(
            receiver_1h,
            on=[
                "to_account_key",
                "event_ts",
            ],
            how="left",
        )
        .join(
            receiver_24h,
            on=[
                "to_account_key",
                "event_ts",
            ],
            how="left",
        )
        .join(
            receiver_7d,
            on=[
                "to_account_key",
                "event_ts",
            ],
            how="left",
        )
        .join(
            sender_first_seen,
            on=[
                "from_account_key",
                "to_account_key",
            ],
            how="left",
        )
        .join(
            receiver_first_seen,
            on=[
                "to_account_key",
                "from_account_key",
            ],
            how="left",
        )
    )

    # ======================================================
    # Fill zero-history windows
    # ======================================================

    counterparty_columns = [
        "sender_unique_receivers_1h",
        "sender_unique_receivers_24h",
        "sender_unique_receivers_7d",
        "receiver_unique_senders_1h",
        "receiver_unique_senders_24h",
        "receiver_unique_senders_7d",
    ]

    features = features.with_columns(
        [
            pl.col(column)
            .fill_null(0)
            for column in counterparty_columns
        ]
    )

    # ======================================================
    # New-counterparty flags
    # ======================================================

    features = features.with_columns(
        [
            (
                pl.col("event_ts")
                == pl.col(
                    "sender_receiver_first_seen_ts"
                )
            )
            .cast(pl.UInt8)
            .alias("new_receiver_for_sender"),

            (
                pl.col("event_ts")
                == pl.col(
                    "receiver_sender_first_seen_ts"
                )
            )
            .cast(pl.UInt8)
            .alias("new_sender_for_receiver"),
        ]
    )

    # ======================================================
    # Fan ratios
    # ======================================================

    features = features.with_columns(
        [
            pl.when(
                pl.col("sender_tx_count_1h") > 0
            )
            .then(
                pl.col("sender_unique_receivers_1h")
                / pl.col("sender_tx_count_1h")
            )
            .otherwise(0.0)
            .alias("sender_fanout_ratio_1h"),

            pl.when(
                pl.col("sender_tx_count_24h") > 0
            )
            .then(
                pl.col("sender_unique_receivers_24h")
                / pl.col("sender_tx_count_24h")
            )
            .otherwise(0.0)
            .alias("sender_fanout_ratio_24h"),

            pl.when(
                pl.col("receiver_tx_count_1h") > 0
            )
            .then(
                pl.col("receiver_unique_senders_1h")
                / pl.col("receiver_tx_count_1h")
            )
            .otherwise(0.0)
            .alias("receiver_fanin_ratio_1h"),

            pl.when(
                pl.col("receiver_tx_count_24h") > 0
            )
            .then(
                pl.col("receiver_unique_senders_24h")
                / pl.col("receiver_tx_count_24h")
            )
            .otherwise(0.0)
            .alias("receiver_fanin_ratio_24h"),
        ]
    )

    print("\nWriting V4 counterparty dataset...")

    features.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()