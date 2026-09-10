from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v3_concentration.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v4_bank.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Bank Network Features")
    print("=" * 90)

    base = pl.scan_parquet(
        INPUT_PATH
    )

    # ======================================================
    # Account keys contain:
    #
    # bank::account
    #
    # But bank IDs are safer extracted from existing
    # original columns if present.
    # ======================================================

    schema = base.collect_schema()

    if (
        "from_bank" not in schema
        or "to_bank" not in schema
    ):

        base = base.with_columns(
            [
                pl.col(
                    "from_account_key"
                )
                .str.split("::")
                .list.first()
                .alias(
                    "from_bank"
                ),

                pl.col(
                    "to_account_key"
                )
                .str.split("::")
                .list.first()
                .alias(
                    "to_bank"
                ),
            ]
        )

    # ======================================================
    # Aggregate transactions at same bank pair + timestamp
    # ======================================================

    bank_pair_ts = (
        base.group_by(
            [
                "from_bank",
                "to_bank",
                "event_ts",
            ]
        )
        .agg(
            [
                pl.len()
                .alias(
                    "bank_pair_tx_at_ts"
                ),

                pl.col(
                    "amount_paid"
                )
                .sum()
                .alias(
                    "bank_pair_amount_at_ts"
                ),
            ]
        )
        .sort(
            [
                "from_bank",
                "to_bank",
                "event_ts",
            ]
        )
    )

    bank_pair_history = (
        bank_pair_ts
        .with_columns(
            [
                (
                    pl.col(
                        "bank_pair_tx_at_ts"
                    )
                    .cum_sum()
                    .over(
                        [
                            "from_bank",
                            "to_bank",
                        ]
                    )
                    -
                    pl.col(
                        "bank_pair_tx_at_ts"
                    )
                )
                .alias(
                    "bank_pair_prior_tx_count"
                ),

                (
                    pl.col(
                        "bank_pair_amount_at_ts"
                    )
                    .cum_sum()
                    .over(
                        [
                            "from_bank",
                            "to_bank",
                        ]
                    )
                    -
                    pl.col(
                        "bank_pair_amount_at_ts"
                    )
                )
                .alias(
                    "bank_pair_prior_amount_sum"
                ),
            ]
        )
    )

    bank_pair_history = (
        bank_pair_history
        .with_columns(
            pl.when(
                pl.col(
                    "bank_pair_prior_tx_count"
                ) > 0
            )
            .then(
                pl.col(
                    "bank_pair_prior_amount_sum"
                )
                /
                pl.col(
                    "bank_pair_prior_tx_count"
                )
            )
            .otherwise(None)
            .alias(
                "bank_pair_prior_amount_avg"
            )
        )
        .select(
            [
                "from_bank",
                "to_bank",
                "event_ts",

                "bank_pair_prior_tx_count",
                "bank_pair_prior_amount_sum",
                "bank_pair_prior_amount_avg",
            ]
        )
    )

    # ======================================================
    # Sender-bank overall historical transaction count
    # ======================================================

    sender_bank_ts = (
        base.group_by(
            [
                "from_bank",
                "event_ts",
            ]
        )
        .agg(
            pl.len()
            .alias(
                "sender_bank_tx_at_ts"
            )
        )
        .sort(
            [
                "from_bank",
                "event_ts",
            ]
        )
        .with_columns(
            (
                pl.col(
                    "sender_bank_tx_at_ts"
                )
                .cum_sum()
                .over(
                    "from_bank"
                )
                -
                pl.col(
                    "sender_bank_tx_at_ts"
                )
            )
            .alias(
                "sender_bank_prior_tx_count"
            )
        )
        .select(
            [
                "from_bank",
                "event_ts",
                "sender_bank_prior_tx_count",
            ]
        )
    )

    # ======================================================
    # Join
    # ======================================================

    features = (
        base
        .join(
            bank_pair_history,
            on=[
                "from_bank",
                "to_bank",
                "event_ts",
            ],
            how="left",
        )
        .join(
            sender_bank_ts,
            on=[
                "from_bank",
                "event_ts",
            ],
            how="left",
        )
    )

    # ======================================================
    # Bank relationship concentration
    # ======================================================

    features = features.with_columns(
        pl.when(
            pl.col(
                "sender_bank_prior_tx_count"
            ) > 0
        )
        .then(
            pl.col(
                "bank_pair_prior_tx_count"
            )
            /
            pl.col(
                "sender_bank_prior_tx_count"
            )
        )
        .otherwise(0.0)
        .alias(
            "bank_pair_share_of_sender_bank_history"
        )
    )

    print("\nWriting graph V4...")

    features.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()