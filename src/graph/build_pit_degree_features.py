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
    / "graph"
    / "transactions_pit_degree.parquet"
)


def main():
    print("=" * 80)
    print("GraphShield AML - Point-in-Time Degree Features")
    print("=" * 80)

    if not INPUT_PATH.exists():
        print("\nERROR: Input dataset not found.")
        print(INPUT_PATH)
        return

    print("\nInput:")
    print(INPUT_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    base = pl.scan_parquet(INPUT_PATH)

    # One row for each sender-receiver relationship.
    # It records when this pair was first observed.
    pair_first_seen = (
        base.group_by(
            [
                "from_account_key",
                "to_account_key",
            ]
        )
        .agg(
            pl.col("event_ts")
            .min()
            .alias("pair_first_seen_ts")
        )
    )

    # Sender degree events:
    # each event represents one NEW unique receiver.
    sender_degree_events = (
        pair_first_seen.group_by(
            [
                "from_account_key",
                "pair_first_seen_ts",
            ]
        )
        .agg(
            pl.len().alias("new_receivers_at_ts")
        )
        .sort(
            [
                "from_account_key",
                "pair_first_seen_ts",
            ]
        )
        .with_columns(
            pl.col("new_receivers_at_ts")
            .cum_sum()
            .over("from_account_key")
            .alias("sender_unique_receivers_cumulative")
        )
        .rename(
            {
                "pair_first_seen_ts": "sender_degree_state_ts",
            }
        )
    )

    # Receiver degree events:
    # each event represents one NEW unique sender.
    receiver_degree_events = (
        pair_first_seen.group_by(
            [
                "to_account_key",
                "pair_first_seen_ts",
            ]
        )
        .agg(
            pl.len().alias("new_senders_at_ts")
        )
        .sort(
            [
                "to_account_key",
                "pair_first_seen_ts",
            ]
        )
        .with_columns(
            pl.col("new_senders_at_ts")
            .cum_sum()
            .over("to_account_key")
            .alias("receiver_unique_senders_cumulative")
        )
        .rename(
            {
                "pair_first_seen_ts": "receiver_degree_state_ts",
            }
        )
    )

    print("\nJoining prior sender degree...")

    # allow_exact_matches=False ensures the current transaction
    # cannot see its own sender-receiver relationship.
    features = (
        base.sort(
            [
                "from_account_key",
                "event_ts",
            ]
        )
        .join_asof(
            sender_degree_events.sort(
                [
                    "from_account_key",
                    "sender_degree_state_ts",
                ]
            ),
            left_on="event_ts",
            right_on="sender_degree_state_ts",
            by="from_account_key",
            strategy="backward",
            allow_exact_matches=False,
        )
    )

    print("Joining prior receiver degree...")

    features = (
        features.sort(
            [
                "to_account_key",
                "event_ts",
            ]
        )
        .join_asof(
            receiver_degree_events.sort(
                [
                    "to_account_key",
                    "receiver_degree_state_ts",
                ]
            ),
            left_on="event_ts",
            right_on="receiver_degree_state_ts",
            by="to_account_key",
            strategy="backward",
            allow_exact_matches=False,
        )
    )

    # New accounts have no earlier relationships, so fill nulls with zero.
    features = features.with_columns(
        [
            pl.col("sender_unique_receivers_cumulative")
            .fill_null(0)
            .cast(pl.Int64)
            .alias("sender_prior_unique_receivers"),

            pl.col("receiver_unique_senders_cumulative")
            .fill_null(0)
            .cast(pl.Int64)
            .alias("receiver_prior_unique_senders"),
        ]
    ).drop(
        [
            "new_receivers_at_ts",
            "sender_unique_receivers_cumulative",
            "sender_degree_state_ts",
            "new_senders_at_ts",
            "receiver_unique_senders_cumulative",
            "receiver_degree_state_ts",
        ]
    )

    print("\nWriting point-in-time degree features...")

    features.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)

    print("\n" + "=" * 80)
    print("POINT-IN-TIME DEGREE FEATURE BUILD COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()