from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v4_bank.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v5_motifs.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Temporal Graph Motifs")
    print("=" * 90)

    base = pl.scan_parquet(
        INPUT_PATH
    )

    # ======================================================
    # Directed pair activity at each timestamp
    # ======================================================

    pair_ts = (
        base
        .group_by(
            [
                "from_account_key",
                "to_account_key",
                "event_ts",
            ]
        )
        .agg(
            [
                pl.len()
                .alias("pair_tx_at_ts_motif"),

                pl.col("amount_paid")
                .sum()
                .alias("pair_amount_at_ts_motif"),
            ]
        )
        .sort(
            [
                "from_account_key",
                "to_account_key",
                "event_ts",
            ]
        )
    )

    # ======================================================
    # Historical state INCLUDING its own timestamp.
    #
    # Because current transaction uses strict as-of <
    # current event_ts, this state becomes legitimate
    # previous history.
    # ======================================================

    reverse_state = (
        pair_ts
        .with_columns(
            [
                pl.col("pair_tx_at_ts_motif")
                .cum_sum()
                .over(
                    [
                        "from_account_key",
                        "to_account_key",
                    ]
                )
                .alias(
                    "reverse_pair_prior_tx_count"
                ),

                pl.col("pair_amount_at_ts_motif")
                .cum_sum()
                .over(
                    [
                        "from_account_key",
                        "to_account_key",
                    ]
                )
                .alias(
                    "reverse_pair_prior_amount_sum"
                ),
            ]
        )
        .select(
            [
                # Reverse keys:
                # historical B -> A
                # current    A -> B
                pl.col("to_account_key")
                .alias("from_account_key"),

                pl.col("from_account_key")
                .alias("to_account_key"),

                pl.col("event_ts")
                .alias(
                    "reverse_pair_prev_event_ts"
                ),

                "reverse_pair_prior_tx_count",
                "reverse_pair_prior_amount_sum",
            ]
        )
        .sort(
            [
                "from_account_key",
                "to_account_key",
                "reverse_pair_prev_event_ts",
            ]
        )
    )

    print("\nJoining reciprocal history...")

    features = (
        base
        .sort(
            [
                "from_account_key",
                "to_account_key",
                "event_ts",
            ]
        )
        .join_asof(
            reverse_state,
            left_on="event_ts",
            right_on="reverse_pair_prev_event_ts",
            by=[
                "from_account_key",
                "to_account_key",
            ],
            strategy="backward",
            allow_exact_matches=False,
        )
        .with_columns(
            [
                pl.col(
                    "reverse_pair_prior_tx_count"
                )
                .fill_null(0),

                pl.col(
                    "reverse_pair_prior_amount_sum"
                )
                .fill_null(0.0),
            ]
        )
    )

    features = features.with_columns(
        [
            (
                pl.col("event_ts")
                -
                pl.col(
                    "reverse_pair_prev_event_ts"
                )
            )
            .dt.total_seconds()
            .alias(
                "reverse_pair_seconds_since_previous"
            ),

            (
                pl.col(
                    "reverse_pair_prior_tx_count"
                ) > 0
            )
            .cast(pl.UInt8)
            .alias(
                "reciprocal_prior_exists"
            ),

            (
                pl.col(
                    "reverse_pair_prior_tx_count"
                ) > 0
            )
            .cast(pl.UInt8)
            .alias(
                "closes_two_node_cycle"
            ),
        ]
    )

    # ======================================================
    # Directional balance
    # ======================================================

    features = features.with_columns(
        pl.when(
            (
                pl.col("pair_prior_tx_count")
                +
                pl.col(
                    "reverse_pair_prior_tx_count"
                )
            ) > 0
        )
        .then(
            pl.min_horizontal(
                [
                    pl.col("pair_prior_tx_count"),
                    pl.col(
                        "reverse_pair_prior_tx_count"
                    ),
                ]
            )
            /
            pl.max_horizontal(
                [
                    pl.col("pair_prior_tx_count"),
                    pl.col(
                        "reverse_pair_prior_tx_count"
                    ),
                ]
            )
        )
        .otherwise(0.0)
        .alias(
            "directional_history_balance"
        )
    )

    # ======================================================
    # First seen for each pair
    # ======================================================

    pair_first_seen = (
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
            .alias("pair_first_seen_ts_motif")
        )
    )

    # ======================================================
    # Current sender's historical IN-degree
    # ======================================================

    sender_in_state = (
        pair_first_seen
        .group_by(
            [
                "to_account_key",
                "pair_first_seen_ts_motif",
            ]
        )
        .agg(
            pl.len()
            .alias("new_in_neighbors_at_ts")
        )
        .sort(
            [
                "to_account_key",
                "pair_first_seen_ts_motif",
            ]
        )
        .with_columns(
            pl.col("new_in_neighbors_at_ts")
            .cum_sum()
            .over("to_account_key")
            .alias(
                "sender_prior_unique_senders"
            )
        )
        .select(
            [
                pl.col("to_account_key")
                .alias("from_account_key"),

                pl.col(
                    "pair_first_seen_ts_motif"
                )
                .alias(
                    "sender_in_degree_state_ts"
                ),

                "sender_prior_unique_senders",
            ]
        )
        .sort(
            [
                "from_account_key",
                "sender_in_degree_state_ts",
            ]
        )
    )

    features = (
        features
        .sort(
            [
                "from_account_key",
                "event_ts",
            ]
        )
        .join_asof(
            sender_in_state,
            left_on="event_ts",
            right_on="sender_in_degree_state_ts",
            by="from_account_key",
            strategy="backward",
            allow_exact_matches=False,
        )
    )

    # ======================================================
    # Current receiver's historical OUT-degree
    # ======================================================

    receiver_out_state = (
        pair_first_seen
        .group_by(
            [
                "from_account_key",
                "pair_first_seen_ts_motif",
            ]
        )
        .agg(
            pl.len()
            .alias("new_out_neighbors_at_ts")
        )
        .sort(
            [
                "from_account_key",
                "pair_first_seen_ts_motif",
            ]
        )
        .with_columns(
            pl.col("new_out_neighbors_at_ts")
            .cum_sum()
            .over("from_account_key")
            .alias(
                "receiver_prior_unique_receivers"
            )
        )
        .select(
            [
                pl.col("from_account_key")
                .alias("to_account_key"),

                pl.col(
                    "pair_first_seen_ts_motif"
                )
                .alias(
                    "receiver_out_degree_state_ts"
                ),

                "receiver_prior_unique_receivers",
            ]
        )
        .sort(
            [
                "to_account_key",
                "receiver_out_degree_state_ts",
            ]
        )
    )

    features = (
        features
        .sort(
            [
                "to_account_key",
                "event_ts",
            ]
        )
        .join_asof(
            receiver_out_state,
            left_on="event_ts",
            right_on="receiver_out_degree_state_ts",
            by="to_account_key",
            strategy="backward",
            allow_exact_matches=False,
        )
        .with_columns(
            [
                pl.col(
                    "sender_prior_unique_senders"
                )
                .fill_null(0),

                pl.col(
                    "receiver_prior_unique_receivers"
                )
                .fill_null(0),
            ]
        )
    )

    # ======================================================
    # Bridge-style degree
    # ======================================================

    features = features.with_columns(
        [
            pl.min_horizontal(
                [
                    pl.col(
                        "sender_prior_unique_senders"
                    ),
                    pl.col(
                        "sender_prior_unique_receivers"
                    ),
                ]
            )
            .alias(
                "sender_bridge_degree"
            ),

            pl.min_horizontal(
                [
                    pl.col(
                        "receiver_prior_unique_senders"
                    ),
                    pl.col(
                        "receiver_prior_unique_receivers"
                    ),
                ]
            )
            .alias(
                "receiver_bridge_degree"
            ),
        ]
    )

    print("\nWriting graph V5...")

    features.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()