import json

import joblib
import numpy as np
import polars as pl

from catboost import (
    CatBoostClassifier,
)

from sklearn.linear_model import (
    LogisticRegression,
)

from common import (
    MODEL_DIR,
    PREDICTION_DIR,
    REPORT_DIR,
    ensure_directories,
    get_feature_columns,
    load_tree_split,
)

from metrics import (
    evaluate_binary,
    save_json,
)


def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def logit(probability):

    probability = np.clip(
        probability,
        1e-6,
        1 - 1e-6,
    )

    return np.log(
        probability
        / (
            1 - probability
        )
    )


def catboost_ready(
    X,
    categorical,
):

    X = X.copy()

    for column in categorical:

        X[column] = (
            X[column]
            .astype(str)
        )

    return X


def main():

    ensure_directories()

    print("=" * 80)
    print("GraphShield AML - Champion Calibration")
    print("=" * 80)

    lgb_metrics = load_json(
        REPORT_DIR
        / "lightgbm_validation.json"
    )

    cat_metrics = load_json(
        REPORT_DIR
        / "catboost_validation.json"
    )

    candidates = {
        "lightgbm": lgb_metrics,
        "catboost": cat_metrics,
    }

    champion_name = max(
        candidates,
        key=lambda name: (
            candidates[name][
                "average_precision"
            ],

            candidates[name][
                "recall_at_top_1pct"
            ],
        ),
    )

    print(
        "\nSelected champion:",
        champion_name,
    )

    features, numerical, categorical = (
        get_feature_columns()
    )

    _, X_val, y_val = (
        load_tree_split(
            "validation",
            features,
            numerical,
            categorical,
        )
    )

    ids_test, X_test, y_test = (
        load_tree_split(
            "test",
            features,
            numerical,
            categorical,
        )
    )

    # ======================================================
    # Load champion
    # ======================================================

    if champion_name == "lightgbm":

        model = joblib.load(
            MODEL_DIR
            / "lightgbm_v1.joblib"
        )

    else:

        model = CatBoostClassifier()

        model.load_model(
            str(
                MODEL_DIR
                / "catboost_v1.cbm"
            )
        )

        X_val = catboost_ready(
            X_val,
            categorical,
        )

        X_test = catboost_ready(
            X_test,
            categorical,
        )

    # ======================================================
    # Raw validation scores
    # ======================================================

    raw_val = (
        model.predict_proba(
            X_val
        )[:, 1]
    )

    # ======================================================
    # Platt scaling
    #
    # Fit ONLY on validation.
    # ======================================================

    calibration_X = (
        logit(raw_val)
        .reshape(-1, 1)
    )

    calibrator = LogisticRegression(
        C=1_000_000,
        max_iter=1000,
        solver="lbfgs",
    )

    calibrator.fit(
        calibration_X,
        y_val,
    )

    # ======================================================
    # Final untouched TEST
    # ======================================================

    raw_test = (
        model.predict_proba(
            X_test
        )[:, 1]
    )

    calibrated_test = (
        calibrator.predict_proba(
            logit(
                raw_test
            )
            .reshape(-1, 1)
        )[:, 1]
    )

    raw_metrics = evaluate_binary(
        y_test,
        raw_test,
    )

    calibrated_metrics = (
        evaluate_binary(
            y_test,
            calibrated_test,
        )
    )

    print(
        "\nRaw Brier:",
        raw_metrics[
            "brier_score"
        ],
    )

    print(
        "Calibrated Brier:",
        calibrated_metrics[
            "brier_score"
        ],
    )

    print(
        "\nRaw ECE:",
        raw_metrics[
            "ece_10_bins"
        ],
    )

    print(
        "Calibrated ECE:",
        calibrated_metrics[
            "ece_10_bins"
        ],
    )

    save_json(
        REPORT_DIR
        / "champion_test_metrics.json",
        {
            "champion": (
                champion_name
            ),

            "raw": (
                raw_metrics
            ),

            "calibrated": (
                calibrated_metrics
            ),
        },
    )

    joblib.dump(
        {
            "champion": champion_name,
            "calibrator": calibrator,
        },
        MODEL_DIR
        / "probability_calibrator.joblib",
    )

    (
        MODEL_DIR
        / "champion_name.txt"
    ).write_text(
        champion_name,
        encoding="utf-8",
    )

    pl.DataFrame(
        {
            "transaction_id": (
                ids_test.to_numpy()
            ),

            "is_laundering": (
                y_test
            ),

            "risk_score_raw": (
                raw_test
            ),

            "risk_score_calibrated": (
                calibrated_test
            ),
        }
    ).write_parquet(
        PREDICTION_DIR
        / "champion_test_predictions.parquet",
        compression="zstd",
    )

    print(
        "\nFinal test predictions saved."
    )


if __name__ == "__main__":
    main()