from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BASE_MODEL_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1_split.parquet"
)

GRAPH_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v5_motifs.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)


GRAPH_COLUMNS = [
    # Degree
    "sender_prior_unique_receivers",
    "receiver_prior_unique_senders",

    # Pair history
    "pair_prior_tx_count",
    "pair_prior_amount_sum",
    "pair_prior_amount_avg",
    "pair_seconds_since_previous",
    "pair_relationship_age_seconds",

    # Concentration
    "pair_share_of_sender_history",
    "pair_share_of_receiver_history",
    "graph_new_pair",
    "graph_established_pair",

    # Bank graph
    "bank_pair_prior_tx_count",
    "bank_pair_prior_amount_sum",
    "bank_pair_prior_amount_avg",
    "sender_bank_prior_tx_count",
    "bank_pair_share_of_sender_bank_history",

    # Reciprocal / motifs
    "reverse_pair_prior_tx_count",
    "reverse_pair_prior_amount_sum",
    "reverse_pair_seconds_since_previous",
    "reciprocal_prior_exists",
    "closes_two_node_cycle",
    "directional_history_balance",

    # Cross-role degree
    "sender_prior_unique_senders",
    "receiver_prior_unique_receivers",
    "sender_bridge_degree",
    "receiver_bridge_degree",

    # Validation-only timestamps
    "pair_prev_event_ts",
    "pair_first_event_ts",
    "reverse_pair_prev_event_ts",
    "sender_in_degree_state_ts",
    "receiver_out_degree_state_ts",
]


def main():

    print("=" * 90)
    print("GraphShield AML - Graph Enhanced Model Dataset")
    print("=" * 90)

    base = pl.scan_parquet(
        BASE_MODEL_PATH
    )

    graph = (
        pl.scan_parquet(
            GRAPH_PATH
        )
        .select(
            [
                "transaction_id",
                *GRAPH_COLUMNS,
            ]
        )
    )

    result = base.join(
        graph,
        on="transaction_id",
        how="left",
    )

    print("\nWriting graph-enhanced Gold dataset...")

    result.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    summary = (
        pl.scan_parquet(OUTPUT_PATH)
        .select(
            [
                pl.len()
                .alias("rows"),

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

    print("\n--- SUMMARY ---")
    print(summary)

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
