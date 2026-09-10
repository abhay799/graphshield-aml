from pathlib import Path

import json
import numpy as np
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1_split.parquet"
)

RULE_DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v6_rules.parquet"
)

ML_PREDICTION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
    / "champion_test_predictions.parquet"
)

REPORT_DIR = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
    / "rules_vs_ml_test.parquet"
)


CAPACITIES = [
    0.01,
    0.05,
    0.10,
]


def evaluate_ranking(
    df: pl.DataFrame,
    score_column: str,
):

    df = df.sort(
        [
            score_column,
            "transaction_id",
        ],
        descending=[
            True,
            False,
        ],
    )

    total_rows = df.height

    total_positives = int(
        df["is_laundering"].sum()
    )

    prevalence = (
        total_positives
        / total_rows
    )

    results = {}

    for fraction in CAPACITIES:

        review_count = max(
            1,
            int(
                np.ceil(
                    total_rows
                    * fraction
                )
            ),
        )

        reviewed = df.head(
            review_count
        )

        captured = int(
            reviewed[
                "is_laundering"
            ].sum()
        )

        precision = (
            captured
            / review_count
        )

        recall = (
            captured
            / max(
                total_positives,
                1,
            )
        )

        lift = (
            precision
            / max(
                prevalence,
                1e-12,
            )
        )

        key = (
            f"top_{int(fraction * 100)}pct"
        )

        results[key] = {
            "review_capacity": fraction,
            "reviewed_transactions": (
                review_count
            ),
            "captured_positives": captured,
            "precision": precision,
            "recall": recall,
            "lift": lift,
        }

    return results


def main():

    print("=" * 90)
    print("GraphShield AML - Rules vs ML")
    print("=" * 90)

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ======================================================
    # TEST transactions only
    # ======================================================

    test = (
        pl.scan_parquet(
            MODEL_DATA_PATH
        )
        .filter(
            pl.col("split")
            == "test"
        )
        .select(
            [
                "transaction_id",
                "is_laundering",
            ]
        )
    )

    # ======================================================
    # Rule outputs
    # ======================================================

    rules = (
        pl.scan_parquet(
            RULE_DATA_PATH
        )
        .select(
            [
                "transaction_id",

                "rule_high_velocity",
                "rule_rapid_fan_out",
                "rule_rapid_fan_in",
                "rule_rapid_pass_through",

                "rule_hit_count",
                "any_rule_hit",
            ]
        )
    )

    # Rule priority score.
    #
    # This is NOT a probability.
    #
    # Higher severity rules receive larger
    # deterministic ranking weights.
    rules = rules.with_columns(
        (
            pl.col("rule_high_velocity")
            * 1
            +
            pl.col("rule_rapid_fan_out")
            * 2
            +
            pl.col("rule_rapid_fan_in")
            * 2
            +
            pl.col("rule_rapid_pass_through")
            * 3
        )
        .cast(pl.Float64)
        .alias("rule_priority_score")
    )

    # ======================================================
    # ML predictions
    # ======================================================

    ml = (
        pl.scan_parquet(
            ML_PREDICTION_PATH
        )
        .select(
            [
                "transaction_id",
                "risk_score_raw",
                "risk_score_calibrated",
            ]
        )
    )

    combined = (
        test
        .join(
            rules,
            on="transaction_id",
            how="left",
        )
        .join(
            ml,
            on="transaction_id",
            how="left",
        )
        .collect()
    )

    print(
        f"\nTest transactions: "
        f"{combined.height:,}"
    )

    print(
        "Test positives:",
        int(
            combined[
                "is_laundering"
            ].sum()
        ),
    )

    # ======================================================
    # Missing-score safety checks
    # ======================================================

    null_check = combined.select(
        [
            pl.col(
                "rule_priority_score"
            )
            .null_count()
            .alias(
                "missing_rule_scores"
            ),

            pl.col(
                "risk_score_calibrated"
            )
            .null_count()
            .alias(
                "missing_ml_scores"
            ),
        ]
    )

    print(
        "\n--- JOIN CHECK ---"
    )

    print(null_check)

    # ======================================================
    # Evaluate identical capacity
    # ======================================================

    rule_results = evaluate_ranking(
        combined,
        "rule_priority_score",
    )

    ml_results = evaluate_ranking(
        combined,
        "risk_score_calibrated",
    )

    report = {
        "test_rows": (
            combined.height
        ),

        "test_positives": int(
            combined[
                "is_laundering"
            ].sum()
        ),

        "rules": rule_results,

        "ml": ml_results,
    }

    print(
        "\n--- SAME REVIEW CAPACITY ---"
    )

    for capacity in [
        "top_1pct",
        "top_5pct",
        "top_10pct",
    ]:

        print(
            f"\n{capacity.upper()}"
        )

        print(
            "Rules recall:",
            rule_results[
                capacity
            ]["recall"],
        )

        print(
            "ML recall:",
            ml_results[
                capacity
            ]["recall"],
        )

        print(
            "Rules precision:",
            rule_results[
                capacity
            ]["precision"],
        )

        print(
            "ML precision:",
            ml_results[
                capacity
            ]["precision"],
        )

    with open(
        REPORT_DIR
        / "rules_vs_ml.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
        )

    combined.write_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print(
        "\nSaved:"
    )

    print(
        REPORT_DIR
        / "rules_vs_ml.json"
    )

    print(
        OUTPUT_PATH
    )


if __name__ == "__main__":
    main()