from pathlib import Path
import math

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "temporal"
)

NODE_PATH = (
    OUTPUT_DIR
    / "tgn_node_mapping.parquet"
)

EVENT_PATH = (
    OUTPUT_DIR
    / "tgn_events.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Build TGN Temporal Event Stream")
    print("=" * 90)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not INPUT_PATH.exists():

        print("\nERROR: Graph model dataset missing:")
        print(INPUT_PATH)
        return

    base = pl.scan_parquet(
        INPUT_PATH
    )

    # ======================================================
    # 1. Build global account → integer node mapping
    # ======================================================

    print("\nBuilding node mapping...")

    sender_nodes = (
        base.select(
            pl.col(
                "from_account_key"
            )
            .alias("account_key")
        )
    )

    receiver_nodes = (
        base.select(
            pl.col(
                "to_account_key"
            )
            .alias("account_key")
        )
    )

    nodes = (
        pl.concat(
            [
                sender_nodes,
                receiver_nodes,
            ]
        )
        .unique()
        .sort("account_key")
        .with_row_index(
            "node_id"
        )
        .with_columns(
            pl.col("node_id")
            .cast(pl.Int64)
        )
    )

    nodes.sink_parquet(
        NODE_PATH,
        compression="zstd",
    )

    node_map = pl.scan_parquet(
        NODE_PATH
    )

    # ======================================================
    # 2. Dataset minimum timestamp
    # ======================================================

    minimum_timestamp = (
        base.select(
            pl.col("event_ts").min()
        )
        .collect()
        .item()
    )

    print("\nMinimum timestamp:")
    print(minimum_timestamp)

    # ======================================================
    # 3. Current-event message features
    #
    # Deliberately NOT using target or future data.
    #
    # We also avoid handcrafted graph history here so that
    # TGN has to learn temporal interaction information.
    # ======================================================

    events = (
        base
        .select(
            [
                "transaction_id",
                "event_ts",

                "from_account_key",
                "to_account_key",

                "log_amount_paid",
                "log_amount_received",

                "cross_bank",
                "cross_currency",

                "hour_of_day",
                "day_of_week",

                "same_currency_amount_ratio",

                "split",
                "is_laundering",
            ]
        )
        .with_columns(
            [
                # Hour cyclic encoding
                (
                    pl.col("hour_of_day")
                    * (2 * math.pi / 24)
                )
                .sin()
                .cast(pl.Float32)
                .alias("hour_sin"),

                (
                    pl.col("hour_of_day")
                    * (2 * math.pi / 24)
                )
                .cos()
                .cast(pl.Float32)
                .alias("hour_cos"),

                # Day-of-week cyclic encoding
                (
                    (
                        pl.col("day_of_week") - 1
                    )
                    * (2 * math.pi / 7)
                )
                .sin()
                .cast(pl.Float32)
                .alias("dow_sin"),

                (
                    (
                        pl.col("day_of_week") - 1
                    )
                    * (2 * math.pi / 7)
                )
                .cos()
                .cast(pl.Float32)
                .alias("dow_cos"),

                pl.col(
                    "same_currency_amount_ratio"
                )
                .fill_null(0.0)
                .cast(pl.Float32),

                pl.col("log_amount_paid")
                .fill_null(0.0)
                .cast(pl.Float32),

                pl.col("log_amount_received")
                .fill_null(0.0)
                .cast(pl.Float32),

                pl.col("cross_bank")
                .cast(pl.Float32),

                pl.col("cross_currency")
                .cast(pl.Float32),

                (
                    pl.col("event_ts")
                    - pl.lit(minimum_timestamp)
                )
                .dt.total_seconds()
                .cast(pl.Int64)
                .alias("t_seconds"),
            ]
        )
    )

    # ======================================================
    # 4. Map sender → src node ID
    # ======================================================

    sender_map = (
        node_map.select(
            [
                pl.col("account_key")
                .alias("from_account_key"),

                pl.col("node_id")
                .alias("src"),
            ]
        )
    )

    receiver_map = (
        node_map.select(
            [
                pl.col("account_key")
                .alias("to_account_key"),

                pl.col("node_id")
                .alias("dst"),
            ]
        )
    )

    events = (
        events
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
    )

    # ======================================================
    # 5. Final event schema
    # ======================================================

    events = (
        events
        .select(
            [
                "transaction_id",

                "event_ts",
                "t_seconds",

                "src",
                "dst",

                # TGN message features
                "log_amount_paid",
                "log_amount_received",
                "cross_bank",
                "cross_currency",
                "same_currency_amount_ratio",
                "hour_sin",
                "hour_cos",
                "dow_sin",
                "dow_cos",

                # Evaluation only
                "split",
                "is_laundering",
            ]
        )
        .sort(
            [
                "event_ts",
                "transaction_id",
            ]
        )
    )

    print("\nWriting temporal event stream...")

    events.sink_parquet(
        EVENT_PATH,
        compression="zstd",
    )

    # ======================================================
    # Summary
    # ======================================================

    event_summary = (
        pl.scan_parquet(EVENT_PATH)
        .select(
            [
                pl.len()
                .alias("events"),

                pl.col("transaction_id")
                .n_unique()
                .alias("unique_transactions"),

                pl.col("is_laundering")
                .sum()
                .alias("positives"),

                pl.col("src")
                .max()
                .alias("max_src"),

                pl.col("dst")
                .max()
                .alias("max_dst"),
            ]
        )
        .collect()
    )

    node_count = (
        pl.scan_parquet(NODE_PATH)
        .select(
            pl.len()
            .alias("nodes")
        )
        .collect()
    )

    print("\n--- EVENT SUMMARY ---")
    print(event_summary)

    print("\n--- NODE SUMMARY ---")
    print(node_count)

    print("\nCreated:")
    print(EVENT_PATH)
    print(NODE_PATH)

    print("\n" + "=" * 90)
    print("TGN EVENT BUILD COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()