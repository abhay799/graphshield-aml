from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "silver"
    / "transactions.parquet"
)

GRAPH_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
)

EDGE_PATH = (
    GRAPH_DIR
    / "transaction_edges.parquet"
)

NODE_PATH = (
    GRAPH_DIR
    / "account_nodes.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Build Canonical Graph Tables")
    print("=" * 90)

    GRAPH_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not INPUT_PATH.exists():
        print("\nERROR: Silver transactions missing.")
        print(INPUT_PATH)
        return

    tx = (
        pl.scan_parquet(INPUT_PATH)
        .with_columns(
            [
                pl.concat_str(
                    [
                        pl.col("from_bank"),
                        pl.col("from_account"),
                    ],
                    separator="::",
                )
                .alias("from_account_key"),

                pl.concat_str(
                    [
                        pl.col("to_bank"),
                        pl.col("to_account"),
                    ],
                    separator="::",
                )
                .alias("to_account_key"),
            ]
        )
    )

    # ======================================================
    # Edge table
    # ======================================================

    edges = tx.select(
        [
            "transaction_id",
            "event_ts",

            "from_account_key",
            "to_account_key",

            "from_bank",
            "to_bank",

            "amount_paid",
            "amount_received",

            "payment_currency",
            "receiving_currency",
            "payment_format",

            "is_laundering",
        ]
    )

    print("\nWriting transaction edge table...")

    edges.sink_parquet(
        EDGE_PATH,
        compression="zstd",
    )

    # ======================================================
    # Sender nodes
    # ======================================================

    sender_nodes = (
        tx.select(
            [
                pl.col(
                    "from_account_key"
                )
                .alias("account_key"),

                pl.col(
                    "from_bank"
                )
                .alias("bank_id"),
            ]
        )
    )

    # ======================================================
    # Receiver nodes
    # ======================================================

    receiver_nodes = (
        tx.select(
            [
                pl.col(
                    "to_account_key"
                )
                .alias("account_key"),

                pl.col(
                    "to_bank"
                )
                .alias("bank_id"),
            ]
        )
    )

    nodes = (
        pl.concat(
            [
                sender_nodes,
                receiver_nodes,
            ]
        )
        .unique(
            subset=[
                "account_key",
            ]
        )
    )

    print("Writing account node table...")

    nodes.sink_parquet(
        NODE_PATH,
        compression="zstd",
    )

    # ======================================================
    # Summary
    # ======================================================

    edge_count = (
        pl.scan_parquet(
            EDGE_PATH
        )
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    node_count = (
        pl.scan_parquet(
            NODE_PATH
        )
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    print(
        f"\nEdges: {edge_count:,}"
    )

    print(
        f"Nodes: {node_count:,}"
    )

    print("\nCreated:")
    print(EDGE_PATH)
    print(NODE_PATH)

    print("\n" + "=" * 90)
    print("GRAPH TABLE BUILD COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()
