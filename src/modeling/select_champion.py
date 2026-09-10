from pathlib import Path

import json


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REPORT_DIR = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
)

MODEL_DIR = (
    PROJECT_ROOT
    / "models"
)


def read_json(path):

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def main():

    print("=" * 90)
    print("GraphShield AML - Final Phase 3 Champion Selection")
    print("=" * 90)

    # ======================================================
    # Logistic
    # ======================================================

    logistic = read_json(
        REPORT_DIR
        / "logistic_metrics.json"
    )

    logistic_name = (
        logistic[
            "selected_model"
        ]
    )

    logistic_metrics = (
        logistic[
            "validation_candidates"
        ][
            logistic_name
        ]
    )

    # ======================================================
    # LightGBM
    # ======================================================

    lightgbm = read_json(
        REPORT_DIR
        / "lightgbm_validation.json"
    )

    # ======================================================
    # CatBoost
    # ======================================================

    catboost = read_json(
        REPORT_DIR
        / "catboost_validation.json"
    )

    candidates = {
        "logistic": (
            logistic_metrics
        ),

        "lightgbm": (
            lightgbm
        ),

        "catboost": (
            catboost
        ),
    }

    print(
        "\n--- VALIDATION COMPARISON ---"
    )

    for name, metrics in (
        candidates.items()
    ):

        print(
            f"\n{name.upper()}"
        )

        print(
            "Average Precision:",
            metrics[
                "average_precision"
            ],
        )

        print(
            "Recall@Top1%:",
            metrics[
                "recall_at_top_1pct"
            ],
        )

        print(
            "Recall@Top5%:",
            metrics[
                "recall_at_top_5pct"
            ],
        )

        print(
            "Precision@Top1%:",
            metrics[
                "precision_at_top_1pct"
            ],
        )

        print(
            "ROC-AUC:",
            metrics[
                "roc_auc"
            ],
        )

    # ======================================================
    # Champion
    # ======================================================

    champion = max(
        candidates,
        key=lambda name: (
            candidates[name][
                "average_precision"
            ],

            candidates[name][
                "recall_at_top_1pct"
            ],

            candidates[name][
                "recall_at_top_5pct"
            ],
        ),
    )

    print(
        "\n" + "=" * 90
    )

    print(
        "FINAL PHASE 3 CHAMPION:",
        champion.upper(),
    )

    print(
        "=" * 90
    )

    selection_report = {
        "selection_dataset": (
            "validation"
        ),

        "primary_metric": (
            "average_precision"
        ),

        "secondary_metric": (
            "recall_at_top_1pct"
        ),

        "tertiary_metric": (
            "recall_at_top_5pct"
        ),

        "champion": champion,

        "candidates": candidates,
    }

    with open(
        REPORT_DIR
        / "final_champion_selection.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            selection_report,
            file,
            indent=2,
        )

    (
        MODEL_DIR
        / "final_champion_name.txt"
    ).write_text(
        champion,
        encoding="utf-8",
    )

    print(
        "\nSaved champion selection."
    )


if __name__ == "__main__":
    main()