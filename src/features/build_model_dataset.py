from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v5_passthrough.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1.parquet"
)


MODEL_COLUMNS = [
    # ======================================================
    # Context
    # ======================================================

    "transaction_id",
    "event_ts",
    "from_account_key",
    "to_account_key",

    # ======================================================
    # Basic transaction features
    # ======================================================

    "amount_paid",
    "amount_received",
    "log_amount_paid",
    "log_amount_received",

    "payment_format",
    "payment_currency",
    "receiving_currency",

    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "cross_bank",
    "cross_currency",

    # ======================================================
    # Sender historical features
    # ======================================================

    "sender_prior_tx_count",
    "sender_prior_amount_sum",
    "sender_prior_amount_avg",
    "sender_seconds_since_previous",

    # ======================================================
    # Receiver historical features
    # ======================================================

    "receiver_prior_tx_count",
    "receiver_prior_amount_sum",
    "receiver_prior_amount_avg",
    "receiver_seconds_since_previous",

    # ======================================================
    # Velocity features
    # ======================================================

    "sender_tx_count_1h",
    "sender_tx_count_24h",
    "sender_tx_count_7d",

    "receiver_tx_count_1h",
    "receiver_tx_count_24h",
    "receiver_tx_count_7d",

    # ======================================================
    # Counterparty / network behavior
    # ======================================================

    "sender_unique_receivers_1h",
    "sender_unique_receivers_24h",
    "sender_unique_receivers_7d",

    "receiver_unique_senders_1h",
    "receiver_unique_senders_24h",
    "receiver_unique_senders_7d",

    "sender_fanout_ratio_1h",
    "sender_fanout_ratio_24h",

    "receiver_fanin_ratio_1h",
    "receiver_fanin_ratio_24h",

    "new_receiver_for_sender",
    "new_sender_for_receiver",

    # ======================================================
    # Pass-through features
    # ======================================================

    "sender_recent_inbound_count_1h",
    "sender_recent_inbound_count_24h",

    "recent_inbound_coverage_1h",
    "seconds_since_last_inbound_1h",
    "rapid_pass_through_candidate",

    # ======================================================
    # Validation-only timestamp fields
    #
    # These are kept for leakage validation.
    # Do NOT use them as ML model features later.
    # ======================================================

    "sender_prev_event_ts",
    "receiver_prev_event_ts",
    "sender_last_inbound_ts_1h",

    # ======================================================
    # Target
    # ======================================================

    "is_laundering",
]


def main():

    print("=" * 80)
    print("GraphShield AML - Build Model Dataset V1")
    print("=" * 80)

    # ======================================================
    # Check input file
    # ======================================================

    if not INPUT_PATH.exists():

        print("\nERROR: Input dataset not found.")
        print(INPUT_PATH)

        return

    print("\nInput:")
    print(INPUT_PATH)

    # ======================================================
    # Read dataset
    # ======================================================

    lf = pl.scan_parquet(INPUT_PATH)

    # ======================================================
    # Validate required columns
    # ======================================================

    schema = lf.collect_schema()

    missing_columns = [
        column
        for column in MODEL_COLUMNS
        if column not in schema
    ]

    if missing_columns:

        print("\nERROR: Missing columns in V5 dataset:")

        for column in missing_columns:
            print(f"  - {column}")

        return

    print("\nAll required columns found.")

    # ======================================================
    # Select model + validation columns
    # ======================================================

    lf = lf.select(MODEL_COLUMNS)

    # ======================================================
    # Same-currency amount relationship
    # ======================================================

    lf = lf.with_columns(
        pl.when(
            (
                pl.col("payment_currency")
                == pl.col("receiving_currency")
            )
            &
            (
                pl.col("amount_paid") > 0
            )
        )
        .then(
            pl.col("amount_received")
            / pl.col("amount_paid")
        )
        .otherwise(None)
        .alias("same_currency_amount_ratio")
    )

    # ======================================================
    # Write Gold model dataset
    # ======================================================

    print("\nWriting model dataset...")

    lf.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)

    # ======================================================
    # Verify output
    # ======================================================

    result = (
        pl.scan_parquet(OUTPUT_PATH)
        .select(
            [
                pl.len()
                .alias("rows"),

                pl.col("is_laundering")
                .sum()
                .alias("positives"),

                pl.col("event_ts")
                .min()
                .alias("start"),

                pl.col("event_ts")
                .max()
                .alias("end"),
            ]
        )
        .collect()
    )

    print("\n--- MODEL DATASET SUMMARY ---")
    print(result)

    print("\n" + "=" * 80)
    print("MODEL DATASET V1 BUILD COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()