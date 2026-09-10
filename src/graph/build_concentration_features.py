from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v2_pair.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v3_concentration.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Graph Concentration Features")
    print("=" * 90)

    lf = pl.scan_parquet(
        INPUT_PATH
    )

    lf = lf.with_columns(
        [
            # ==================================================
            # What fraction of sender history involved
            # this particular receiver?
            # ==================================================

            pl.when(
                pl.col(
                    "sender_prior_tx_count"
                ) > 0
            )
            .then(
                pl.col(
                    "pair_prior_tx_count"
                )
                /
                pl.col(
                    "sender_prior_tx_count"
                )
            )
            .otherwise(0.0)
            .alias(
                "pair_share_of_sender_history"
            ),

            # ==================================================
            # What fraction of receiver history came
            # from this sender?
            # ==================================================

            pl.when(
                pl.col(
                    "receiver_prior_tx_count"
                ) > 0
            )
            .then(
                pl.col(
                    "pair_prior_tx_count"
                )
                /
                pl.col(
                    "receiver_prior_tx_count"
                )
            )
            .otherwise(0.0)
            .alias(
                "pair_share_of_receiver_history"
            ),
        ]
    )

    # ======================================================
    # Novel / established relationship buckets
    # ======================================================

    lf = lf.with_columns(
        [
            (
                pl.col(
                    "pair_prior_tx_count"
                ) == 0
            )
            .cast(pl.UInt8)
            .alias(
                "graph_new_pair"
            ),

            (
                pl.col(
                    "pair_prior_tx_count"
                ) >= 10
            )
            .cast(pl.UInt8)
            .alias(
                "graph_established_pair"
            ),
        ]
    )

    print("\nWriting graph V3...")

    lf.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()