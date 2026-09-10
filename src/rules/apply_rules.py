from pathlib import Path

import polars as pl
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v5_passthrough.parquet"
)

RULE_PATH = (
    PROJECT_ROOT
    / "configs"
    / "rules"
    / "transaction_rules.yaml"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v6_rules.parquet"
)


def load_rules():

    with open(
        RULE_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        return yaml.safe_load(file)["rules"]


def main():

    print("=" * 80)
    print("GraphShield AML - Rule Engine")
    print("=" * 80)

    rules = load_rules()

    lf = pl.scan_parquet(INPUT_PATH)

    # ======================================================
    # HIGH VELOCITY
    # ======================================================

    threshold = rules[
        "HIGH_VELOCITY"
    ]["sender_tx_count_1h_min"]

    lf = lf.with_columns(
        (
            pl.col("sender_tx_count_1h")
            >= threshold
        )
        .cast(pl.UInt8)
        .alias("rule_high_velocity")
    )

    # ======================================================
    # RAPID FAN OUT
    # ======================================================

    rule = rules["RAPID_FAN_OUT"]

    lf = lf.with_columns(
        (
            (
                pl.col("sender_tx_count_1h")
                >= rule["sender_tx_count_1h_min"]
            )
            &
            (
                pl.col("sender_unique_receivers_1h")
                >= rule[
                    "sender_unique_receivers_1h_min"
                ]
            )
            &
            (
                pl.col("sender_fanout_ratio_1h")
                >= rule[
                    "sender_fanout_ratio_1h_min"
                ]
            )
        )
        .cast(pl.UInt8)
        .alias("rule_rapid_fan_out")
    )

    # ======================================================
    # RAPID FAN IN
    # ======================================================

    rule = rules["RAPID_FAN_IN"]

    lf = lf.with_columns(
        (
            (
                pl.col("receiver_tx_count_1h")
                >= rule["receiver_tx_count_1h_min"]
            )
            &
            (
                pl.col("receiver_unique_senders_1h")
                >= rule[
                    "receiver_unique_senders_1h_min"
                ]
            )
            &
            (
                pl.col("receiver_fanin_ratio_1h")
                >= rule[
                    "receiver_fanin_ratio_1h_min"
                ]
            )
        )
        .cast(pl.UInt8)
        .alias("rule_rapid_fan_in")
    )

    # ======================================================
    # RAPID PASS THROUGH
    # ======================================================

    lf = lf.with_columns(
        (
            pl.col("rapid_pass_through_candidate")
            == 1
        )
        .cast(pl.UInt8)
        .alias("rule_rapid_pass_through")
    )

    # ======================================================
    # Aggregate rule information
    # ======================================================

    rule_columns = [
        "rule_high_velocity",
        "rule_rapid_fan_out",
        "rule_rapid_fan_in",
        "rule_rapid_pass_through",
    ]

    lf = lf.with_columns(
        pl.sum_horizontal(
            [
                pl.col(column)
                for column in rule_columns
            ]
        )
        .cast(pl.UInt8)
        .alias("rule_hit_count")
    )

    lf = lf.with_columns(
        (
            pl.col("rule_hit_count") > 0
        )
        .cast(pl.UInt8)
        .alias("any_rule_hit")
    )

    print("\nWriting rule-enriched transactions...")

    lf.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)

    # Summary
    summary = (
        pl.scan_parquet(OUTPUT_PATH)
        .select(
            [
                pl.len().alias("transactions"),

                pl.col("any_rule_hit")
                .sum()
                .alias("transactions_with_alerts"),

                *[
                    pl.col(column)
                    .sum()
                    .alias(column)
                    for column in rule_columns
                ],
            ]
        )
        .collect()
    )

    print("\n--- RULE SUMMARY ---")

    print(summary)


if __name__ == "__main__":
    main()