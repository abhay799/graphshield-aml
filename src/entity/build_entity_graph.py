from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

EDGE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "transaction_edges.parquet"
)

MAP_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "entities"
    / "account_entity_map.parquet"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "entities"
)

ENTITY_EDGE_PATH = (
    OUTPUT_DIR
    / "entity_edges.parquet"
)

PAIR_SUMMARY_PATH = (
    OUTPUT_DIR
    / "entity_pair_summary.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Entity Transaction Graph")
    print("=" * 90)

    edges = pl.scan_parquet(
        EDGE_PATH
    )

    mapping = pl.scan_parquet(
        MAP_PATH
    )

    sender_map = (
        mapping.select(
            [
                pl.col("account_key")
                .alias(
                    "from_account_key"
                ),

                pl.col("entity_id")
                .alias(
                    "src_entity_id"
                ),
            ]
        )
    )

    receiver_map = (
        mapping.select(
            [
                pl.col("account_key")
                .alias(
                    "to_account_key"
                ),

                pl.col("entity_id")
                .alias(
                    "dst_entity_id"
                ),
            ]
        )
    )

    entity_edges = (
        edges
        .join(
            sender_map,
            on="from_account_key",
            how="left",
        )
        .join(
            receiver_map,
            on="to_account_key",
            how="left",
        )
        .select(
            [
                "transaction_id",
                "event_ts",

                "src_entity_id",
                "dst_entity_id",

                "from_account_key",
                "to_account_key",

                "from_bank",
                "to_bank",

                "amount_paid",
                "amount_received",

                "payment_currency",
                "receiving_currency",
                "payment_format",
            ]
        )
    )

    print("\nWriting entity edges...")

    entity_edges.sink_parquet(
        ENTITY_EDGE_PATH,
        compression="zstd",
    )

    # ======================================================
    # Full-period investigation summary.
    #
    # IMPORTANT:
    # investigation-only, not an ML feature.
    # ======================================================

    pair_summary = (
        pl.scan_parquet(
            ENTITY_EDGE_PATH
        )
        .group_by(
            [
                "src_entity_id",
                "dst_entity_id",
            ]
        )
        .agg(
            [
                pl.len()
                .alias(
                    "transaction_count"
                ),

                pl.col("amount_paid")
                .sum()
                .alias(
                    "total_amount_paid"
                ),

                pl.col("amount_paid")
                .mean()
                .alias(
                    "avg_amount_paid"
                ),

                pl.col("event_ts")
                .min()
                .alias(
                    "first_event_ts"
                ),

                pl.col("event_ts")
                .max()
                .alias(
                    "last_event_ts"
                ),

                pl.col(
                    "payment_currency"
                )
                .n_unique()
                .alias(
                    "currency_count"
                ),
            ]
        )
    )

    pair_summary.sink_parquet(
        PAIR_SUMMARY_PATH,
        compression="zstd",
    )

    summary = (
        pl.scan_parquet(
            ENTITY_EDGE_PATH
        )
        .select(
            [
                pl.len()
                .alias("edges"),

                pl.col(
                    "transaction_id"
                )
                .n_unique()
                .alias(
                    "unique_transactions"
                ),

                pl.col(
                    "src_entity_id"
                )
                .null_count()
                .alias(
                    "missing_src_entities"
                ),

                pl.col(
                    "dst_entity_id"
                )
                .null_count()
                .alias(
                    "missing_dst_entities"
                ),
            ]
        )
        .collect()
    )

    print("\n--- ENTITY GRAPH ---")
    print(summary)


if __name__ == "__main__":
    main()