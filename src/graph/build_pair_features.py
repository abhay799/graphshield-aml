from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v1_degree.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v2_pair.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Pair Relationship Features")
    print("=" * 90)

    base = pl.scan_parquet(
        INPUT_PATH
    )

    # ======================================================
    # Preaggregate same directed pair + timestamp
    # ======================================================

    pair_ts = (
        base.group_by(
            [
                "from_account_key",
                "to_account_key",
                "event_ts",
            ]
        )
        .agg(
            [
                pl.len()
                .alias(
                    "pair_tx_at_ts"
                ),

                pl.col(
                    "amount_paid"
                )
                .sum()
                .alias(
                    "pair_amount_at_ts"
                ),
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
    # Point-in-time lifetime pair history
    # ======================================================

    pair_history = (
        pair_ts
        .with_columns(
            [
                (
                    pl.col(
                        "pair_tx_at_ts"
                    )
                    .cum_sum()
                    .over(
                        [
                            "from_account_key",
                            "to_account_key",
                        ]
                    )
                    -
                    pl.col(
                        "pair_tx_at_ts"
                    )
                )
                .alias(
                    "pair_prior_tx_count"
                ),

                (
                    pl.col(
                        "pair_amount_at_ts"
                    )
                    .cum_sum()
                    .over(
                        [
                            "from_account_key",
                            "to_account_key",
                        ]
                    )
                    -
                    pl.col(
                        "pair_amount_at_ts"
                    )
                )
                .alias(
                    "pair_prior_amount_sum"
                ),

                pl.col("event_ts")
                .shift(1)
                .over(
                    [
                        "from_account_key",
                        "to_account_key",
                    ]
                )
                .alias(
                    "pair_prev_event_ts"
                ),

                pl.col("event_ts")
                .first()
                .over(
                    [
                        "from_account_key",
                        "to_account_key",
                    ]
                )
                .alias(
                    "pair_first_event_ts"
                ),
            ]
        )
    )

    pair_history = (
        pair_history
        .with_columns(
            [
                pl.when(
                    pl.col(
                        "pair_prior_tx_count"
                    ) > 0
                )
                .then(
                    pl.col(
                        "pair_prior_amount_sum"
                    )
                    /
                    pl.col(
                        "pair_prior_tx_count"
                    )
                )
                .otherwise(None)
                .alias(
                    "pair_prior_amount_avg"
                ),

                (
                    pl.col("event_ts")
                    -
                    pl.col(
                        "pair_prev_event_ts"
                    )
                )
                .dt.total_seconds()
                .alias(
                    "pair_seconds_since_previous"
                ),

                (
                    pl.col("event_ts")
                    -
                    pl.col(
                        "pair_first_event_ts"
                    )
                )
                .dt.total_seconds()
                .alias(
                    "pair_relationship_age_seconds"
                ),
            ]
        )
    )

    pair_history = pair_history.select(
        [
            "from_account_key",
            "to_account_key",
            "event_ts",

            "pair_prior_tx_count",
            "pair_prior_amount_sum",
            "pair_prior_amount_avg",

            "pair_prev_event_ts",
            "pair_first_event_ts",

            "pair_seconds_since_previous",
            "pair_relationship_age_seconds",
        ]
    )

    print(
        "\nJoining pair history..."
    )

    features = base.join(
        pair_history,
        on=[
            "from_account_key",
            "to_account_key",
            "event_ts",
        ],
        how="left",
    )

    print("\nWriting graph V2...")

    features.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()