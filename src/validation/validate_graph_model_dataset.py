from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Graph Point-in-Time Validation")
    print("=" * 90)

    lf = pl.scan_parquet(PATH)

    print("\n--- INTEGRITY ---")

    print(
        lf.select(
            [
                pl.len().alias("rows"),

                pl.col("transaction_id")
                .n_unique()
                .alias("unique_ids"),

                pl.col("is_laundering")
                .sum()
                .alias("positives"),
            ]
        )
        .collect()
    )

    print("\n--- TEMPORAL LEAKAGE ---")

    temporal = (
        lf.select(
            [
                (
                    pl.col("sender_in_degree_state_ts")
                    >= pl.col("event_ts")
                )
                .fill_null(False)
                .sum()
                .alias("invalid_sender_degree_ts"),

                (
                    pl.col("receiver_out_degree_state_ts")
                    >= pl.col("event_ts")
                )
                .fill_null(False)
                .sum()
                .alias("invalid_receiver_degree_ts"),

                (
                    pl.col("pair_prev_event_ts")
                    >= pl.col("event_ts")
                )
                .fill_null(False)
                .sum()
                .alias("invalid_pair_previous_ts"),

                (
                    pl.col("reverse_pair_prev_event_ts")
                    >= pl.col("event_ts")
                )
                .fill_null(False)
                .sum()
                .alias("invalid_reverse_pair_ts"),

                (
                    pl.col("sender_in_degree_state_ts")
                    >= pl.col("event_ts")
                )
                .fill_null(False)
                .sum()
                .alias("invalid_sender_in_degree_ts"),

                (
                    pl.col("receiver_out_degree_state_ts")
                    >= pl.col("event_ts")
                )
                .fill_null(False)
                .sum()
                .alias("invalid_receiver_out_degree_ts"),
            ]
        )
        .collect()
    )

    print(temporal)

    print("\n--- COUNT CONSISTENCY ---")

    counts = (
        lf.select(
            [
                (
                    pl.col("sender_prior_unique_receivers")
                    > pl.col("sender_prior_tx_count")
                )
                .sum()
                .alias("sender_degree_gt_tx"),

                (
                    pl.col("receiver_prior_unique_senders")
                    > pl.col("receiver_prior_tx_count")
                )
                .sum()
                .alias("receiver_degree_gt_tx"),

                (
                    pl.col("pair_prior_tx_count")
                    > pl.col("sender_prior_tx_count")
                )
                .sum()
                .alias("pair_gt_sender_history"),

                (
                    pl.col("pair_prior_tx_count")
                    > pl.col("receiver_prior_tx_count")
                )
                .sum()
                .alias("pair_gt_receiver_history"),

                (
                    pl.col("bank_pair_prior_tx_count")
                    > pl.col("sender_bank_prior_tx_count")
                )
                .sum()
                .alias("bank_pair_gt_bank_history"),
            ]
        )
        .collect()
    )

    print(counts)

    print("\n--- FLAG CONSISTENCY ---")

    flags = (
        lf.select(
            [
                (
                    pl.col("graph_new_pair")
                    !=
                    (
                        pl.col("pair_prior_tx_count")
                        == 0
                    ).cast(pl.UInt8)
                )
                .sum()
                .alias("invalid_new_pair_flag"),

                (
                    pl.col("reciprocal_prior_exists")
                    !=
                    (
                        pl.col("reverse_pair_prior_tx_count")
                        > 0
                    ).cast(pl.UInt8)
                )
                .sum()
                .alias("invalid_reciprocal_flag"),

                (
                    pl.col("closes_two_node_cycle")
                    !=
                    pl.col("reciprocal_prior_exists")
                )
                .sum()
                .alias("invalid_cycle_flag"),
            ]
        )
        .collect()
    )

    print(flags)

    print("\n--- RANGE CHECKS ---")

    ranges = (
        lf.select(
            [
                (
                    (
                        pl.col("pair_share_of_sender_history") < 0
                    )
                    |
                    (
                        pl.col("pair_share_of_sender_history") > 1
                    )
                )
                .sum()
                .alias("invalid_sender_pair_share"),

                (
                    (
                        pl.col("pair_share_of_receiver_history") < 0
                    )
                    |
                    (
                        pl.col("pair_share_of_receiver_history") > 1
                    )
                )
                .sum()
                .alias("invalid_receiver_pair_share"),

                (
                    (
                        pl.col("directional_history_balance") < 0
                    )
                    |
                    (
                        pl.col("directional_history_balance") > 1
                    )
                )
                .sum()
                .alias("invalid_direction_balance"),

                (
                    pl.col("pair_relationship_age_seconds") < 0
                )
                .sum()
                .alias("negative_relationship_age"),
            ]
        )
        .collect()
    )

    print(ranges)

    print(
        "\nExpected: every violation count = 0."
    )


if __name__ == "__main__":
    main()
