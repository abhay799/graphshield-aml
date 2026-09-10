from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v2_history.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v3_velocity.parquet"
)

# Set True for testing. Set False after the test succeeds.
DEV_MODE = False
DEV_ROWS = 250_000


def build_sender_timestamp_table(base: pl.LazyFrame) -> pl.LazyFrame:
    """One row per sender account and timestamp."""

    return (
        base.select(
            [
                "from_account_key",
                "event_ts",
                "amount_paid",
            ]
        )
        .group_by(
            [
                "from_account_key",
                "event_ts",
            ]
        )
        .agg(
            [
                pl.len().alias("sender_tx_at_ts"),
                pl.col("amount_paid").sum().alias("sender_amount_at_ts"),
            ]
        )
        .sort(
            [
                "from_account_key",
                "event_ts",
            ]
        )
    )


def build_receiver_timestamp_table(base: pl.LazyFrame) -> pl.LazyFrame:
    """One row per receiver account and timestamp."""

    return (
        base.select(
            [
                "to_account_key",
                "event_ts",
                "amount_received",
            ]
        )
        .group_by(
            [
                "to_account_key",
                "event_ts",
            ]
        )
        .agg(
            [
                pl.len().alias("receiver_tx_at_ts"),
                pl.col("amount_received").sum().alias("receiver_amount_at_ts"),
            ]
        )
        .sort(
            [
                "to_account_key",
                "event_ts",
            ]
        )
    )


def sender_window(
    sender_ts: pl.LazyFrame,
    period: str,
    suffix: str,
) -> pl.LazyFrame:
    """Build sender rolling window features, excluding current timestamp."""

    return (
        sender_ts.rolling(
            index_column="event_ts",
            period=period,
            group_by="from_account_key",
            closed="left",
        )
        .agg(
            [
                pl.col("sender_tx_at_ts")
                .sum()
                .alias(f"sender_tx_count_{suffix}"),
                pl.col("sender_amount_at_ts")
                .sum()
                .alias(f"sender_amount_sum_{suffix}"),
            ]
        )
        .with_columns(
            [
                pl.col(f"sender_tx_count_{suffix}").fill_null(0),
                pl.col(f"sender_amount_sum_{suffix}").fill_null(0.0),
            ]
        )
    )


def receiver_window(
    receiver_ts: pl.LazyFrame,
    period: str,
    suffix: str,
) -> pl.LazyFrame:
    """Build receiver rolling window features, excluding current timestamp."""

    return (
        receiver_ts.rolling(
            index_column="event_ts",
            period=period,
            group_by="to_account_key",
            closed="left",
        )
        .agg(
            [
                pl.col("receiver_tx_at_ts")
                .sum()
                .alias(f"receiver_tx_count_{suffix}"),
                pl.col("receiver_amount_at_ts")
                .sum()
                .alias(f"receiver_amount_sum_{suffix}"),
            ]
        )
        .with_columns(
            [
                pl.col(f"receiver_tx_count_{suffix}").fill_null(0),
                pl.col(f"receiver_amount_sum_{suffix}").fill_null(0.0),
            ]
        )
    )


def main():
    print("=" * 80)
    print("GraphShield AML - Rolling Velocity Feature Engineering")
    print("=" * 80)

    if not INPUT_PATH.exists():
        print("\nERROR: Historical feature dataset not found.")
        print(INPUT_PATH)
        return

    print("\nInput:")
    print(INPUT_PATH)

    base = pl.scan_parquet(INPUT_PATH)

    if DEV_MODE:
        print(f"\nDEV MODE enabled: using first {DEV_ROWS:,} transactions.")
        base = base.head(DEV_ROWS)
    else:
        print("\nFULL DATASET MODE enabled.")

    print("\nBuilding sender timestamp table...")
    sender_ts = build_sender_timestamp_table(base)

    print("Building receiver timestamp table...")
    receiver_ts = build_receiver_timestamp_table(base)

    print("\nBuilding sender 1-hour velocity...")
    sender_1h = sender_window(sender_ts, period="1h", suffix="1h")

    print("Building sender 24-hour velocity...")
    sender_24h = sender_window(sender_ts, period="24h", suffix="24h")

    print("Building sender 7-day velocity...")
    sender_7d = sender_window(sender_ts, period="7d", suffix="7d")

    print("\nBuilding receiver 1-hour velocity...")
    receiver_1h = receiver_window(receiver_ts, period="1h", suffix="1h")

    print("Building receiver 24-hour velocity...")
    receiver_24h = receiver_window(receiver_ts, period="24h", suffix="24h")

    print("Building receiver 7-day velocity...")
    receiver_7d = receiver_window(receiver_ts, period="7d", suffix="7d")

    print("\nJoining rolling features...")

    features = (
        base.join(
            sender_1h,
            on=["from_account_key", "event_ts"],
            how="left",
        )
        .join(
            sender_24h,
            on=["from_account_key", "event_ts"],
            how="left",
        )
        .join(
            sender_7d,
            on=["from_account_key", "event_ts"],
            how="left",
        )
        .join(
            receiver_1h,
            on=["to_account_key", "event_ts"],
            how="left",
        )
        .join(
            receiver_24h,
            on=["to_account_key", "event_ts"],
            how="left",
        )
        .join(
            receiver_7d,
            on=["to_account_key", "event_ts"],
            how="left",
        )
    )

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

    features = features.with_columns(
        [
            pl.col(column).fill_null(0)
            for column in velocity_columns
        ]
    )

    print("\n--- VELOCITY FEATURES ---")

    schema = features.collect_schema()

    for column in velocity_columns:
        print(f"{column:<35}{schema[column]}")

    print("\nWriting velocity feature dataset...")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    features.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)

    print("\n" + "=" * 80)
    print("VELOCITY FEATURE BUILD COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()