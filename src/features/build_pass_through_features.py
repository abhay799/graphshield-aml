from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v4_counterparty.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v5_passthrough.parquet"
)


DEV_MODE = False
DEV_ROWS = 250_000


def inbound_window(
    inbound: pl.LazyFrame,
    period: str,
    suffix: str,
) -> pl.LazyFrame:

    return (
        inbound
        .rolling(
            index_column="event_ts",
            period=period,
            group_by=[
                "to_account_key",
                "receiving_currency",
            ],
            closed="left",
        )
        .agg(
            [
                pl.col("inbound_tx_at_ts")
                .sum()
                .alias(
                    f"sender_recent_inbound_count_{suffix}"
                ),

                pl.col("inbound_amount_at_ts")
                .sum()
                .alias(
                    f"sender_recent_inbound_amount_{suffix}"
                ),

                pl.col("inbound_event_ts")
                .max()
                .alias(
                    f"sender_last_inbound_ts_{suffix}"
                ),
            ]
        )
    )


def main():

    print("=" * 80)
    print("GraphShield AML - Rapid Pass-Through Features")
    print("=" * 80)

    if not INPUT_PATH.exists():
        print("\nERROR: V4 dataset missing.")
        return

    base = pl.scan_parquet(INPUT_PATH)

    if DEV_MODE:
        print(
            f"\nDEV MODE: first {DEV_ROWS:,} rows"
        )

        base = base.head(DEV_ROWS)

    # ======================================================
    # Historical inbound transactions
    # ======================================================

    inbound = (
        base
        .select(
            [
                "to_account_key",
                "receiving_currency",
                "event_ts",
                "amount_received",
            ]
        )
        .group_by(
            [
                "to_account_key",
                "receiving_currency",
                "event_ts",
            ]
        )
        .agg(
            [
                pl.len()
                .alias("inbound_tx_at_ts"),

                pl.col("amount_received")
                .sum()
                .alias("inbound_amount_at_ts"),
            ]
        )
        .with_columns(
            pl.col("event_ts")
            .alias("inbound_event_ts")
        )
        .sort(
            [
                "to_account_key",
                "receiving_currency",
                "event_ts",
            ]
        )
    )

    print("\nBuilding inbound 1-hour history...")

    inbound_1h = inbound_window(
        inbound,
        "1h",
        "1h",
    )

    print("Building inbound 24-hour history...")

    inbound_24h = inbound_window(
        inbound,
        "24h",
        "24h",
    )

    # ======================================================
    # Join previous inbound history to CURRENT SENDER
    # ======================================================

    features = (
        base
        .join(
            inbound_1h,
            left_on=[
                "from_account_key",
                "payment_currency",
                "event_ts",
            ],
            right_on=[
                "to_account_key",
                "receiving_currency",
                "event_ts",
            ],
            how="left",
        )
        .join(
            inbound_24h,
            left_on=[
                "from_account_key",
                "payment_currency",
                "event_ts",
            ],
            right_on=[
                "to_account_key",
                "receiving_currency",
                "event_ts",
            ],
            how="left",
        )
    )

    # ======================================================
    # Nulls mean no previous inbound transactions
    # ======================================================

    features = features.with_columns(
        [
            pl.col("sender_recent_inbound_count_1h")
            .fill_null(0),

            pl.col("sender_recent_inbound_amount_1h")
            .fill_null(0.0),

            pl.col("sender_recent_inbound_count_24h")
            .fill_null(0),

            pl.col("sender_recent_inbound_amount_24h")
            .fill_null(0.0),
        ]
    )

    # ======================================================
    # Time since last recent inbound transaction
    # ======================================================

    features = features.with_columns(
        [
            (
                pl.col("event_ts")
                - pl.col("sender_last_inbound_ts_1h")
            )
            .dt.total_seconds()
            .alias(
                "seconds_since_last_inbound_1h"
            ),

            (
                pl.col("event_ts")
                - pl.col("sender_last_inbound_ts_24h")
            )
            .dt.total_seconds()
            .alias(
                "seconds_since_last_inbound_24h"
            ),
        ]
    )

    # ======================================================
    # How much of current outbound could recent inbound cover?
    # ======================================================

    features = features.with_columns(
        pl.when(
            pl.col("amount_paid") > 0
        )
        .then(
            pl.when(
                pl.col(
                    "sender_recent_inbound_amount_1h"
                )
                >= pl.col("amount_paid")
            )
            .then(1.0)
            .otherwise(
                pl.col(
                    "sender_recent_inbound_amount_1h"
                )
                / pl.col("amount_paid")
            )
        )
        .otherwise(0.0)
        .alias("recent_inbound_coverage_1h")
    )

    # ======================================================
    # Candidate heuristic
    # ======================================================

    features = features.with_columns(
        (
            (
                pl.col(
                    "sender_recent_inbound_count_1h"
                ) > 0
            )
            &
            (
                pl.col(
                    "recent_inbound_coverage_1h"
                ) >= 0.80
            )
            &
            (
                pl.col(
                    "seconds_since_last_inbound_1h"
                ) <= 3600
            )
        )
        .fill_null(False)
        .cast(pl.UInt8)
        .alias("rapid_pass_through_candidate")
    )

    print("\nWriting V5...")

    features.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()