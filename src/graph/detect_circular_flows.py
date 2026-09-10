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

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "circular_flow_candidates_v1.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Reciprocal / Circular Flow Candidates")
    print("=" * 90)

    edges = pl.scan_parquet(
        EDGE_PATH
    )

    pair_stats = (
        edges
        .group_by(
            [
                "from_account_key",
                "to_account_key",
            ]
        )
        .agg(
            [
                pl.len()
                .alias("forward_tx_count"),

                pl.col("amount_paid")
                .sum()
                .alias("forward_amount_sum"),

                pl.col("event_ts")
                .min()
                .alias("forward_first_ts"),

                pl.col("event_ts")
                .max()
                .alias("forward_last_ts"),
            ]
        )
    )

    reverse_stats = (
        pair_stats.select(
            [
                pl.col("to_account_key")
                .alias("from_account_key"),

                pl.col("from_account_key")
                .alias("to_account_key"),

                pl.col("forward_tx_count")
                .alias("reverse_tx_count"),

                pl.col("forward_amount_sum")
                .alias("reverse_amount_sum"),

                pl.col("forward_first_ts")
                .alias("reverse_first_ts"),

                pl.col("forward_last_ts")
                .alias("reverse_last_ts"),
            ]
        )
    )

    reciprocal = (
        pair_stats
        .join(
            reverse_stats,
            on=[
                "from_account_key",
                "to_account_key",
            ],
            how="inner",
        )
        .filter(
            pl.col("from_account_key")
            < pl.col("to_account_key")
        )
        .with_columns(
            [
                (
                    pl.col("forward_tx_count")
                    +
                    pl.col("reverse_tx_count")
                )
                .alias("cycle_total_tx_count"),

                (
                    pl.col("forward_amount_sum")
                    +
                    pl.col("reverse_amount_sum")
                )
                .alias("cycle_total_amount"),
            ]
        )
    )

    reciprocal.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    summary = (
        pl.scan_parquet(OUTPUT_PATH)
        .select(
            [
                pl.len()
                .alias("reciprocal_pairs"),

                pl.col("cycle_total_tx_count")
                .max()
                .alias("max_cycle_transactions"),
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