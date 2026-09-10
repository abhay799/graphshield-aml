from pathlib import Path

import numpy as np
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]


FEATURE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1_split.parquet"
)


PREDICTION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
    / "champion_test_predictions.parquet"
)


OUTPUT_DIR = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
    / "error_analysis"
)


REVIEW_CAPACITY = 0.01


def main():

    print("=" * 90)
    print("GraphShield AML - Error Analysis")
    print("=" * 90)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ======================================================
    # TEST feature data
    # ======================================================

    features = (
        pl.scan_parquet(
            FEATURE_PATH
        )
        .filter(
            pl.col("split")
            == "test"
        )
    )

    predictions = (
        pl.scan_parquet(
            PREDICTION_PATH
        )
        .select(
            [
                "transaction_id",
                "risk_score_calibrated",
            ]
        )
    )

    df = (
        features
        .join(
            predictions,
            on="transaction_id",
            how="inner",
        )
        .collect()
    )

    print(
        f"\nTest rows: "
        f"{df.height:,}"
    )

    # ======================================================
    # Determine review cutoff
    # ======================================================

    review_count = max(
        1,
        int(
            np.ceil(
                df.height
                * REVIEW_CAPACITY
            )
        ),
    )

    df = df.sort(
        [
            "risk_score_calibrated",
            "transaction_id",
        ],
        descending=[
            True,
            False,
        ],
    )

    df = df.with_row_index(
        "risk_rank",
        offset=1,
    )

    df = df.with_columns(
        (
            pl.col("risk_rank")
            <= review_count
        )
        .cast(pl.UInt8)
        .alias("reviewed")
    )

    # ======================================================
    # Operational outcome classes
    # ======================================================

    df = df.with_columns(
        pl.when(
            (
                pl.col("reviewed") == 1
            )
            &
            (
                pl.col("is_laundering") == 1
            )
        )
        .then(
            pl.lit(
                "captured_positive"
            )
        )

        .when(
            (
                pl.col("reviewed") == 1
            )
            &
            (
                pl.col("is_laundering") == 0
            )
        )
        .then(
            pl.lit(
                "reviewed_negative"
            )
        )

        .when(
            (
                pl.col("reviewed") == 0
            )
            &
            (
                pl.col("is_laundering") == 1
            )
        )
        .then(
            pl.lit(
                "missed_positive"
            )
        )

        .otherwise(
            pl.lit(
                "correctly_deprioritized"
            )
        )

        .alias(
            "operational_outcome"
        )
    )

    # ======================================================
    # Outcome summary
    # ======================================================

    summary = (
        df.group_by(
            "operational_outcome"
        )
        .agg(
            [
                pl.len()
                .alias("transactions"),

                pl.col(
                    "risk_score_calibrated"
                )
                .mean()
                .alias(
                    "avg_risk_score"
                ),

                pl.col(
                    "amount_paid"
                )
                .median()
                .alias(
                    "median_amount_paid"
                ),

                pl.col(
                    "sender_tx_count_1h"
                )
                .mean()
                .alias(
                    "avg_sender_velocity_1h"
                ),

                pl.col(
                    "sender_unique_receivers_1h"
                )
                .mean()
                .alias(
                    "avg_unique_receivers_1h"
                ),

                pl.col(
                    "recent_inbound_coverage_1h"
                )
                .mean()
                .alias(
                    "avg_inbound_coverage"
                ),
            ]
        )
        .sort(
            "transactions",
            descending=True,
        )
    )

    print(
        "\n--- OPERATIONAL OUTCOMES ---"
    )

    print(summary)

    summary.write_csv(
        OUTPUT_DIR
        / "outcome_summary.csv"
    )

    # ======================================================
    # Save missed laundering transactions
    # ======================================================

    missed = (
        df.filter(
            pl.col(
                "operational_outcome"
            )
            == "missed_positive"
        )
        .sort(
            "risk_score_calibrated",
            descending=True,
        )
    )

    missed.write_parquet(
        OUTPUT_DIR
        / "missed_positives.parquet",
        compression="zstd",
    )

    print(
        "\nMissed positives:",
        missed.height,
    )

    # ======================================================
    # Save captured positives
    # ======================================================

    captured = (
        df.filter(
            pl.col(
                "operational_outcome"
            )
            == "captured_positive"
        )
    )

    captured.write_parquet(
        OUTPUT_DIR
        / "captured_positives.parquet",
        compression="zstd",
    )

    # ======================================================
    # False-positive-like reviewed negatives
    # ======================================================

    reviewed_negatives = (
        df.filter(
            pl.col(
                "operational_outcome"
            )
            == "reviewed_negative"
        )
        .head(10_000)
    )

    reviewed_negatives.write_parquet(
        OUTPUT_DIR
        / "reviewed_negatives_sample.parquet",
        compression="zstd",
    )

    # ======================================================
    # Categorical error analysis
    # ======================================================

    payment_format_analysis = (
        df.filter(
            pl.col(
                "operational_outcome"
            )
            .is_in(
                [
                    "captured_positive",
                    "missed_positive",
                ]
            )
        )
        .group_by(
            [
                "payment_format",
                "operational_outcome",
            ]
        )
        .agg(
            pl.len()
            .alias("transactions")
        )
        .sort(
            "transactions",
            descending=True,
        )
    )

    payment_format_analysis.write_csv(
        OUTPUT_DIR
        / "positive_errors_by_payment_format.csv"
    )

    currency_analysis = (
        df.filter(
            pl.col(
                "operational_outcome"
            )
            .is_in(
                [
                    "captured_positive",
                    "missed_positive",
                ]
            )
        )
        .group_by(
            [
                "payment_currency",
                "operational_outcome",
            ]
        )
        .agg(
            pl.len()
            .alias("transactions")
        )
        .sort(
            "transactions",
            descending=True,
        )
    )

    currency_analysis.write_csv(
        OUTPUT_DIR
        / "positive_errors_by_currency.csv"
    )

    # ======================================================
    # Useful feature comparison
    # ======================================================

    feature_analysis = (
        df.filter(
            pl.col(
                "operational_outcome"
            )
            .is_in(
                [
                    "captured_positive",
                    "missed_positive",
                ]
            )
        )
        .group_by(
            "operational_outcome"
        )
        .agg(
            [
                pl.len()
                .alias("transactions"),

                pl.col(
                    "amount_paid"
                )
                .mean()
                .alias(
                    "avg_amount_paid"
                ),

                pl.col(
                    "sender_tx_count_24h"
                )
                .mean()
                .alias(
                    "avg_sender_tx_24h"
                ),

                pl.col(
                    "receiver_tx_count_24h"
                )
                .mean()
                .alias(
                    "avg_receiver_tx_24h"
                ),

                pl.col(
                    "sender_unique_receivers_24h"
                )
                .mean()
                .alias(
                    "avg_sender_unique_receivers"
                ),

                pl.col(
                    "receiver_unique_senders_24h"
                )
                .mean()
                .alias(
                    "avg_receiver_unique_senders"
                ),

                pl.col(
                    "new_receiver_for_sender"
                )
                .mean()
                .alias(
                    "new_counterparty_rate"
                ),

                pl.col(
                    "rapid_pass_through_candidate"
                )
                .mean()
                .alias(
                    "pass_through_rate"
                ),
            ]
        )
    )

    feature_analysis.write_csv(
        OUTPUT_DIR
        / "captured_vs_missed_features.csv"
    )

    print(
        "\nError-analysis files saved to:"
    )

    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()