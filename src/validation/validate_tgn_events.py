from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVENT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "temporal"
    / "tgn_events.parquet"
)

NODE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "temporal"
    / "tgn_node_mapping.parquet"
)


MESSAGE_COLUMNS = [
    "log_amount_paid",
    "log_amount_received",
    "cross_bank",
    "cross_currency",
    "same_currency_amount_ratio",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]


def main():

    print("=" * 90)
    print("GraphShield AML - TGN Event Validation")
    print("=" * 90)

    if not EVENT_PATH.exists():

        print("\nERROR: TGN events missing.")
        print(EVENT_PATH)
        return

    events = pl.scan_parquet(
        EVENT_PATH
    )

    nodes = pl.scan_parquet(
        NODE_PATH
    )

    # ======================================================
    # Integrity
    # ======================================================

    integrity = (
        events.select(
            [
                pl.len()
                .alias("events"),

                pl.col("transaction_id")
                .n_unique()
                .alias(
                    "unique_transaction_ids"
                ),

                pl.col("is_laundering")
                .sum()
                .alias("positives"),

                pl.col("src")
                .min()
                .alias("min_src"),

                pl.col("dst")
                .min()
                .alias("min_dst"),

                pl.col("t_seconds")
                .min()
                .alias("min_time"),

                pl.col("t_seconds")
                .max()
                .alias("max_time"),
            ]
        )
        .collect()
    )

    print("\n--- EVENT INTEGRITY ---")
    print(integrity)

    node_info = (
        nodes.select(
            [
                pl.len()
                .alias("nodes"),

                pl.col("node_id")
                .min()
                .alias("min_node_id"),

                pl.col("node_id")
                .max()
                .alias("max_node_id"),
            ]
        )
        .collect()
    )

    print("\n--- NODE MAPPING ---")
    print(node_info)

    # ======================================================
    # Null message values
    # ======================================================

    nulls = (
        events.select(
            [
                pl.col(column)
                .null_count()
                .alias(column)
                for column in MESSAGE_COLUMNS
            ]
        )
        .collect()
    )

    print("\n--- MESSAGE NULLS ---")
    print(nulls)

    # ======================================================
    # Node ID validity
    # ======================================================

    node_count = (
        nodes.select(
            pl.len()
        )
        .collect()
        .item()
    )

    node_checks = (
        events.select(
            [
                (
                    pl.col("src") < 0
                )
                .sum()
                .alias("negative_src"),

                (
                    pl.col("dst") < 0
                )
                .sum()
                .alias("negative_dst"),

                (
                    pl.col("src")
                    >= node_count
                )
                .sum()
                .alias("src_out_of_range"),

                (
                    pl.col("dst")
                    >= node_count
                )
                .sum()
                .alias("dst_out_of_range"),
            ]
        )
        .collect()
    )

    print("\n--- NODE ID CHECKS ---")
    print(node_checks)

    # ======================================================
    # Temporal ordering
    # ======================================================

    temporal = (
        events.select(
            (
                pl.col("t_seconds")
                .diff()
                < 0
            )
            .fill_null(False)
            .sum()
            .alias(
                "backward_time_events"
            )
        )
        .collect()
    )

    print("\n--- TEMPORAL ORDER ---")
    print(temporal)

    # ======================================================
    # Split chronology
    # ======================================================

    split_ranges = (
        events
        .group_by("split")
        .agg(
            [
                pl.len()
                .alias("events"),

                pl.col("event_ts")
                .min()
                .alias("start"),

                pl.col("event_ts")
                .max()
                .alias("end"),

                pl.col("is_laundering")
                .sum()
                .alias("positives"),
            ]
        )
        .sort("start")
        .collect()
    )

    print("\n--- SPLIT CHRONOLOGY ---")
    print(split_ranges)

    print("\nExpected:")
    print("  message nulls        = 0")
    print("  invalid node IDs     = 0")
    print("  backward time events = 0")

    print("\n" + "=" * 90)
    print("TGN EVENT VALIDATION COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()