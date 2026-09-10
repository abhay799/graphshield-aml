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
    / "account_profiles.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Account Node Profiles")
    print("=" * 90)

    edges = pl.scan_parquet(
        EDGE_PATH
    )

    # ======================================================
    # Outgoing behavior
    # ======================================================

    outgoing = (
        edges.group_by(
            "from_account_key"
        )
        .agg(
            [
                pl.len()
                .alias(
                    "total_outgoing_tx"
                ),

                pl.col("amount_paid")
                .sum()
                .alias(
                    "total_outgoing_amount"
                ),

                pl.col("amount_paid")
                .mean()
                .alias(
                    "avg_outgoing_amount"
                ),

                pl.col(
                    "to_account_key"
                )
                .n_unique()
                .alias(
                    "unique_receivers"
                ),

                pl.col("event_ts")
                .min()
                .alias(
                    "first_outgoing_ts"
                ),

                pl.col("event_ts")
                .max()
                .alias(
                    "last_outgoing_ts"
                ),
            ]
        )
        .rename(
            {
                "from_account_key":
                    "account_key"
            }
        )
    )

    # ======================================================
    # Incoming behavior
    # ======================================================

    incoming = (
        edges.group_by(
            "to_account_key"
        )
        .agg(
            [
                pl.len()
                .alias(
                    "total_incoming_tx"
                ),

                pl.col(
                    "amount_received"
                )
                .sum()
                .alias(
                    "total_incoming_amount"
                ),

                pl.col(
                    "amount_received"
                )
                .mean()
                .alias(
                    "avg_incoming_amount"
                ),

                pl.col(
                    "from_account_key"
                )
                .n_unique()
                .alias(
                    "unique_senders"
                ),

                pl.col("event_ts")
                .min()
                .alias(
                    "first_incoming_ts"
                ),

                pl.col("event_ts")
                .max()
                .alias(
                    "last_incoming_ts"
                ),
            ]
        )
        .rename(
            {
                "to_account_key":
                    "account_key"
            }
        )
    )

    # ======================================================
    # Combine both directions
    # ======================================================

    profiles = (
        outgoing
        .join(
            incoming,
            on="account_key",
            how="full",
            coalesce=True,
        )
        .with_columns(
            [
                pl.col(
                    "total_outgoing_tx"
                )
                .fill_null(0),

                pl.col(
                    "total_incoming_tx"
                )
                .fill_null(0),

                pl.col(
                    "total_outgoing_amount"
                )
                .fill_null(0.0),

                pl.col(
                    "total_incoming_amount"
                )
                .fill_null(0.0),

                pl.col(
                    "unique_receivers"
                )
                .fill_null(0),

                pl.col(
                    "unique_senders"
                )
                .fill_null(0),
            ]
        )
    )

    # ======================================================
    # Basic graph degree
    # ======================================================

    profiles = profiles.with_columns(
        [
            (
                pl.col(
                    "unique_receivers"
                )
                +
                pl.col(
                    "unique_senders"
                )
            )
            .alias(
                "total_neighbor_degree"
            ),

            (
                pl.col(
                    "total_outgoing_tx"
                )
                +
                pl.col(
                    "total_incoming_tx"
                )
            )
            .alias(
                "total_transaction_degree"
            ),
        ]
    )

    print("\nWriting node profiles...")

    profiles.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()