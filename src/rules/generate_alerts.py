from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v6_rules.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "rule_alerts_v1.parquet"
)


def build_alerts(
    lf: pl.LazyFrame,
    flag_column: str,
    rule_id: str,
    severity: str,
    reason: str,
):

    return (
        lf
        .filter(
            pl.col(flag_column) == 1
        )
        .select(
            [
                "transaction_id",
                "event_ts",
                "from_account_key",
                "to_account_key",
                "amount_paid",
                "payment_currency",
                "payment_format",
            ]
        )
        .with_columns(
            [
                pl.lit(rule_id)
                .alias("rule_id"),

                pl.lit(severity)
                .alias("severity"),

                pl.lit(reason)
                .alias("reason"),

                pl.concat_str(
                    [
                        pl.col("transaction_id"),
                        pl.lit("::"),
                        pl.lit(rule_id),
                    ]
                )
                .alias("alert_id"),

                pl.lit("rules_v1")
                .alias("rule_version"),
            ]
        )
    )


def main():

    print("=" * 80)
    print("GraphShield AML - Generate Rule Alerts")
    print("=" * 80)

    lf = pl.scan_parquet(INPUT_PATH)

    alerts = [
        build_alerts(
            lf,
            "rule_high_velocity",
            "HIGH_VELOCITY",
            "medium",
            "High recent transaction velocity.",
        ),

        build_alerts(
            lf,
            "rule_rapid_fan_out",
            "RAPID_FAN_OUT",
            "high",
            "Rapid transfers to multiple distinct recipients.",
        ),

        build_alerts(
            lf,
            "rule_rapid_fan_in",
            "RAPID_FAN_IN",
            "high",
            "Rapid receipts from multiple distinct senders.",
        ),

        build_alerts(
            lf,
            "rule_rapid_pass_through",
            "RAPID_PASS_THROUGH",
            "high",
            "Recent same-currency inbound funds followed by outbound movement.",
        ),
    ]

    alert_lf = pl.concat(
        alerts,
        how="vertical",
    )

    print("\nWriting alerts...")

    alert_lf.sink_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)

    summary = (
        pl.scan_parquet(OUTPUT_PATH)
        .group_by(
            [
                "rule_id",
                "severity",
            ]
        )
        .agg(
            pl.len()
            .alias("alerts")
        )
        .sort(
            "alerts",
            descending=True
        )
        .collect()
    )

    print("\n--- ALERT SUMMARY ---")

    print(summary)


if __name__ == "__main__":
    main()