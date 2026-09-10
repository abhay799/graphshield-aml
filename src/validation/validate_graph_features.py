from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v4_bank.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Graph Feature Validation")
    print("=" * 90)

    lf = pl.scan_parquet(PATH)

    # ======================================================
    # Basic dataset integrity
    # ======================================================

    basic = (
        lf.select(
            [
                pl.len()
                .alias("rows"),

                pl.col(
                    "transaction_id"
                )
                .n_unique()
                .alias(
                    "unique_transaction_ids"
                ),

                pl.col(
                    "is_laundering"
                )
                .sum()
                .alias("positives"),
            ]
        )
        .collect()
    )

    print(
        "\n--- DATASET INTEGRITY ---"
    )

    print(basic)

    # ======================================================
    # Negative-value checks
    # ======================================================

    checks = (
        lf.select(
            [
                (
                    pl.col(
                        "sender_prior_unique_receivers"
                    ) < 0
                )
                .sum()
                .alias(
                    "negative_sender_degree"
                ),

                (
                    pl.col(
                        "receiver_prior_unique_senders"
                    ) < 0
                )
                .sum()
                .alias(
                    "negative_receiver_degree"
                ),

                (
                    pl.col(
                        "pair_prior_tx_count"
                    ) < 0
                )
                .sum()
                .alias(
                    "negative_pair_count"
                ),

                (
                    pl.col(
                        "pair_prior_amount_sum"
                    ) < 0
                )
                .sum()
                .alias(
                    "negative_pair_amount"
                ),

                (
                    pl.col(
                        "pair_relationship_age_seconds"
                    ) < 0
                )
                .sum()
                .alias(
                    "negative_relationship_age"
                ),

                (
                    (
                        pl.col(
                            "pair_share_of_sender_history"
                        ) < 0
                    )
                    |
                    (
                        pl.col(
                            "pair_share_of_sender_history"
                        ) > 1
                    )
                )
                .sum()
                .alias(
                    "invalid_sender_pair_share"
                ),

                (
                    (
                        pl.col(
                            "pair_share_of_receiver_history"
                        ) < 0
                    )
                    |
                    (
                        pl.col(
                            "pair_share_of_receiver_history"
                        ) > 1
                    )
                )
                .sum()
                .alias(
                    "invalid_receiver_pair_share"
                ),

                (
                    (
                        pl.col(
                            "bank_pair_share_of_sender_bank_history"
                        ) < 0
                    )
                    |
                    (
                        pl.col(
                            "bank_pair_share_of_sender_bank_history"
                        ) > 1
                    )
                )
                .sum()
                .alias(
                    "invalid_bank_share"
                ),
            ]
        )
        .collect()
    )

    print(
        "\n--- LOGICAL CHECKS ---"
    )

    print(checks)

    # ======================================================
    # Relationship timestamps
    # ======================================================

    temporal = (
        lf.select(
            [
                (
                    pl.col(
                        "pair_prev_event_ts"
                    )
                    >=
                    pl.col(
                        "event_ts"
                    )
                )
                .fill_null(False)
                .sum()
                .alias(
                    "invalid_pair_previous_ts"
                ),

                (
                    pl.col(
                        "pair_first_event_ts"
                    )
                    >
                    pl.col(
                        "event_ts"
                    )
                )
                .fill_null(False)
                .sum()
                .alias(
                    "future_pair_first_seen"
                ),
            ]
        )
        .collect()
    )

    print(
        "\n--- TEMPORAL CHECKS ---"
    )

    print(temporal)

    print(
        "\nAll violation counts should be 0."
    )

    print("\n" + "=" * 90)
    print("GRAPH FEATURE VALIDATION COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()