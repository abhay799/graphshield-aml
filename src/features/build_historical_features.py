from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v1.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v2_history.parquet"
)

# Set True for a quick test. Set False for all 5+ million rows.
DEV_MODE = False
DEV_ROWS = 250_000


def build_sender_history(base: pl.LazyFrame) -> pl.LazyFrame:
    print("Building sender historical features...")

    sender_ts = (
        base.select(
            [
                "from_account_key",
                "event_ts",
                "amount_paid",
            ]
        )
        .group_by(["from_account_key", "event_ts"])
        .agg(
            [
                pl.len().alias("sender_tx_at_ts"),
                pl.col("amount_paid").sum().alias("sender_amount_at_ts"),
            ]
        )
        .sort(["from_account_key", "event_ts"])
    )

    sender_ts = sender_ts.with_columns(
        [
            (
                pl.col("sender_tx_at_ts").cum_sum().over("from_account_key")
                - pl.col("sender_tx_at_ts")
            ).alias("sender_prior_tx_count"),
            (
                pl.col("sender_amount_at_ts").cum_sum().over("from_account_key")
                - pl.col("sender_amount_at_ts")
            ).alias("sender_prior_amount_sum"),
            pl.col("event_ts")
            .shift(1)
            .over("from_account_key")
            .alias("sender_prev_event_ts"),
        ]
    )

    return sender_ts.with_columns(
        [
            (pl.col("sender_prior_tx_count") > 0)
            .cast(pl.UInt8)
            .alias("sender_has_history"),
            pl.when(pl.col("sender_prior_tx_count") > 0)
            .then(
                pl.col("sender_prior_amount_sum")
                / pl.col("sender_prior_tx_count")
            )
            .otherwise(None)
            .alias("sender_prior_amount_avg"),
            (
                pl.col("event_ts") - pl.col("sender_prev_event_ts")
            )
            .dt.total_seconds()
            .alias("sender_seconds_since_previous"),
        ]
    ).select(
        [
            "from_account_key",
            "event_ts",
            "sender_prior_tx_count",
            "sender_prior_amount_sum",
            "sender_prior_amount_avg",
            "sender_has_history",
            "sender_prev_event_ts",
            "sender_seconds_since_previous",
        ]
    )


def build_receiver_history(base: pl.LazyFrame) -> pl.LazyFrame:
    print("Building receiver historical features...")

    receiver_ts = (
        base.select(
            [
                "to_account_key",
                "event_ts",
                "amount_received",
            ]
        )
        .group_by(["to_account_key", "event_ts"])
        .agg(
            [
                pl.len().alias("receiver_tx_at_ts"),
                pl.col("amount_received").sum().alias("receiver_amount_at_ts"),
            ]
        )
        .sort(["to_account_key", "event_ts"])
    )

    receiver_ts = receiver_ts.with_columns(
        [
            (
                pl.col("receiver_tx_at_ts").cum_sum().over("to_account_key")
                - pl.col("receiver_tx_at_ts")
            ).alias("receiver_prior_tx_count"),
            (
                pl.col("receiver_amount_at_ts").cum_sum().over("to_account_key")
                - pl.col("receiver_amount_at_ts")
            ).alias("receiver_prior_amount_sum"),
            pl.col("event_ts")
            .shift(1)
            .over("to_account_key")
            .alias("receiver_prev_event_ts"),
        ]
    )

    return receiver_ts.with_columns(
        [
            (pl.col("receiver_prior_tx_count") > 0)
            .cast(pl.UInt8)
            .alias("receiver_has_history"),
            pl.when(pl.col("receiver_prior_tx_count") > 0)
            .then(
                pl.col("receiver_prior_amount_sum")
                / pl.col("receiver_prior_tx_count")
            )
            .otherwise(None)
            .alias("receiver_prior_amount_avg"),
            (
                pl.col("event_ts") - pl.col("receiver_prev_event_ts")
            )
            .dt.total_seconds()
            .alias("receiver_seconds_since_previous"),
        ]
    ).select(
        [
            "to_account_key",
            "event_ts",
            "receiver_prior_tx_count",
            "receiver_prior_amount_sum",
            "receiver_prior_amount_avg",
            "receiver_has_history",
            "receiver_prev_event_ts",
            "receiver_seconds_since_previous",
        ]
    )


def main():
    print("=" * 78)
    print("GraphShield AML - Point-in-Time Historical Features")
    print("=" * 78)

    if not INPUT_PATH.exists():
        print("\nERROR: Transaction feature dataset not found.")
        print(INPUT_PATH)
        return

    print("\nInput:")
    print(INPUT_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Scan V1 dataset and create missing unique account keys.
    base = pl.scan_parquet(INPUT_PATH).with_columns(
        [
            pl.concat_str(
                [
                    pl.col("from_bank").cast(pl.String),
                    pl.col("from_account").cast(pl.String),
                ],
                separator="::",
            ).alias("from_account_key"),
            pl.concat_str(
                [
                    pl.col("to_bank").cast(pl.String),
                    pl.col("to_account").cast(pl.String),
                ],
                separator="::",
            ).alias("to_account_key"),
        ]
    )

    if DEV_MODE:
        print(f"\nDEV MODE enabled: using first {DEV_ROWS:,} rows.")
        base = base.head(DEV_ROWS)
    else:
        print("\nFULL DATASET MODE enabled.")

    sender_history = build_sender_history(base)
    receiver_history = build_receiver_history(base)

    print("\nJoining historical features...")

    features = (
        base.join(
            sender_history,
            on=["from_account_key", "event_ts"],
            how="left",
        )
        .join(
            receiver_history,
            on=["to_account_key", "event_ts"],
            how="left",
        )
    )

    print("\n--- OUTPUT SCHEMA ---")
    schema = features.collect_schema()

    for column in schema.names():
        print(f"{column:<35}{schema[column]}")

    print("\nWriting historical feature dataset...")

    features.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)
    print("\n" + "=" * 78)
    print("HISTORICAL FEATURE BUILD COMPLETE")
    print("=" * 78)


if __name__ == "__main__":
    main()