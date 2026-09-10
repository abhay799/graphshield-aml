from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1_split.parquet"
)


def main():

    print("=" * 80)
    print("GraphShield AML - Point-in-Time / Leakage Validation")
    print("=" * 80)

    lf = pl.scan_parquet(PATH)

    # ======================================================
    # 1. Chronological split integrity
    # ======================================================

    print("\n--- TEMPORAL SPLIT RANGES ---")

    ranges = (
        lf.group_by("split")
        .agg(
            [
                pl.col("event_ts")
                .min()
                .alias("start"),

                pl.col("event_ts")
                .max()
                .alias("end"),

                pl.len()
                .alias("rows"),

                pl.col("is_laundering")
                .sum()
                .alias("positives"),
            ]
        )
        .collect()
    )

    print(ranges)

    # ======================================================
    # 2. Historical timestamps must be strictly earlier
    # ======================================================

    print("\n--- PREVIOUS EVENT LEAKAGE ---")

    previous_time_checks = (
        lf.select(
            [
                (
                    pl.col("sender_prev_event_ts")
                    >= pl.col("event_ts")
                )
                .fill_null(False)
                .sum()
                .alias(
                    "invalid_sender_previous_ts"
                ),

                (
                    pl.col("receiver_prev_event_ts")
                    >= pl.col("event_ts")
                )
                .fill_null(False)
                .sum()
                .alias(
                    "invalid_receiver_previous_ts"
                ),

                (
                    pl.col("sender_last_inbound_ts_1h")
                    >= pl.col("event_ts")
                )
                .fill_null(False)
                .sum()
                .alias(
                    "invalid_last_inbound_ts"
                ),
            ]
        )
        .collect()
    )

    print(previous_time_checks)

    # ======================================================
    # 3. Window hierarchy
    # ======================================================

    print("\n--- WINDOW HIERARCHY ---")

    window_checks = (
        lf.select(
            [
                (
                    pl.col("sender_tx_count_1h")
                    > pl.col("sender_tx_count_24h")
                )
                .sum()
                .alias("sender_1h_gt_24h"),

                (
                    pl.col("sender_tx_count_24h")
                    > pl.col("sender_tx_count_7d")
                )
                .sum()
                .alias("sender_24h_gt_7d"),

                (
                    pl.col("receiver_tx_count_1h")
                    > pl.col("receiver_tx_count_24h")
                )
                .sum()
                .alias("receiver_1h_gt_24h"),

                (
                    pl.col("receiver_tx_count_24h")
                    > pl.col("receiver_tx_count_7d")
                )
                .sum()
                .alias("receiver_24h_gt_7d"),
            ]
        )
        .collect()
    )

    print(window_checks)

    # ======================================================
    # 4. Rolling history <= lifetime previous history
    # ======================================================

    print("\n--- HISTORY CONSISTENCY ---")

    history_checks = (
        lf.select(
            [
                (
                    pl.col("sender_tx_count_7d")
                    > pl.col("sender_prior_tx_count")
                )
                .sum()
                .alias(
                    "sender_7d_gt_lifetime_prior"
                ),

                (
                    pl.col("receiver_tx_count_7d")
                    > pl.col("receiver_prior_tx_count")
                )
                .sum()
                .alias(
                    "receiver_7d_gt_lifetime_prior"
                ),
            ]
        )
        .collect()
    )

    print(history_checks)

    # ======================================================
    # 5. Counterparty logical checks
    # ======================================================

    print("\n--- COUNTERPARTY CONSISTENCY ---")

    counterparties = (
        lf.select(
            [
                (
                    pl.col(
                        "sender_unique_receivers_1h"
                    )
                    > pl.col(
                        "sender_tx_count_1h"
                    )
                )
                .sum()
                .alias(
                    "invalid_sender_unique"
                ),

                (
                    pl.col(
                        "receiver_unique_senders_1h"
                    )
                    > pl.col(
                        "receiver_tx_count_1h"
                    )
                )
                .sum()
                .alias(
                    "invalid_receiver_unique"
                ),
            ]
        )
        .collect()
    )

    print(counterparties)

    # ======================================================
    # 6. Pass-through coverage
    # ======================================================

    print("\n--- PASS-THROUGH FEATURE RANGE ---")

    passthrough = (
        lf.select(
            [
                (
                    (
                        pl.col(
                            "recent_inbound_coverage_1h"
                        ) < 0
                    )
                    |
                    (
                        pl.col(
                            "recent_inbound_coverage_1h"
                        ) > 1
                    )
                )
                .sum()
                .alias(
                    "invalid_inbound_coverage"
                )
            ]
        )
        .collect()
    )

    print(passthrough)

    # ======================================================
    # Final
    # ======================================================

    print("\nExpected result:")
    print(
        "All leakage/logical violation counts should be 0."
    )

    print("\n" + "=" * 80)
    print("LEAKAGE VALIDATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
