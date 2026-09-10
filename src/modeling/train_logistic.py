import os

import joblib

from sklearn.impute import SimpleImputer
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from common import (
    MODEL_DIR,
    REPORT_DIR,
    ensure_directories,
    get_feature_columns,
    load_numeric_split,
)

from metrics import (
    evaluate_binary,
    save_json,
)


TRAIN_FRACTION = float(
    os.getenv(
        "GS_LOGISTIC_TRAIN_FRACTION",
        "1.0",
    )
)


def build_model(class_weight):

    return Pipeline(
        [
            (
                "imputer",
                SimpleImputer(
                    strategy="median",
                ),
            ),

            (
                "scaler",
                StandardScaler(),
            ),

            (
                "classifier",
                SGDClassifier(
                    loss="log_loss",
                    class_weight=class_weight,
                    max_iter=100,
                    tol=1e-4,
                    average=True,
                    random_state=42,
                ),
            ),
        ]
    )


def main():

    ensure_directories()

    print("=" * 80)
    print("GraphShield AML - Logistic Baseline")
    print("=" * 80)

    _, numerical, _ = (
        get_feature_columns()
    )

    print(
        f"\nNumerical features: "
        f"{len(numerical)}"
    )

    print(
        f"Training fraction: "
        f"{TRAIN_FRACTION}"
    )

    _, X_train, y_train = (
        load_numeric_split(
            "train",
            numerical,
            TRAIN_FRACTION,
        )
    )

    _, X_val, y_val = (
        load_numeric_split(
            "validation",
            numerical,
        )
    )

    print(
        f"\nTrain rows: "
        f"{len(y_train):,}"
    )

    print(
        f"Train positives: "
        f"{y_train.sum():,}"
    )

    candidates = {}

    # ======================================================
    # 3.3 Standard logistic baseline
    # ======================================================

    for name, weight in [
        (
            "logistic_unweighted",
            None,
        ),
        (
            "logistic_balanced",
            "balanced",
        ),
    ]:

        print(
            f"\nTraining {name}..."
        )

        model = build_model(
            class_weight=weight
        )

        model.fit(
            X_train,
            y_train,
        )

        probability = (
            model.predict_proba(
                X_val
            )[:, 1]
        )

        metrics = evaluate_binary(
            y_val,
            probability,
        )

        candidates[name] = {
            "model": model,
            "metrics": metrics,
        }

        print(
            "Validation AP:",
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

        joblib.dump(
            model,
            MODEL_DIR
            / f"{name}.joblib",
        )

    # ======================================================
    # Choose using VALIDATION only
    # ======================================================

    champion_name = max(
        candidates,
        key=lambda name: (
            candidates[name][
                "metrics"
            ][
                "average_precision"
            ],
            candidates[name][
                "metrics"
            ][
                "recall_at_top_1pct"
            ],
        ),
    )

    print(
        "\nLogistic champion:",
        champion_name,
    )

    champion = candidates[
        champion_name
    ]["model"]

    # Test only the selected logistic model
    _, X_test, y_test = (
        load_numeric_split(
            "test",
            numerical,
        )
    )

    test_probability = (
        champion.predict_proba(
            X_test
        )[:, 1]
    )

    test_metrics = evaluate_binary(
        y_test,
        test_probability,
    )

    report = {
        "training_fraction": (
            TRAIN_FRACTION
        ),

        "numerical_features": (
            numerical
        ),

        "validation_candidates": {
            name: item["metrics"]
            for name, item
            in candidates.items()
        },

        "selected_model": (
            champion_name
        ),

        "selected_test_metrics": (
            test_metrics
        ),
    }

    save_json(
        REPORT_DIR
        / "logistic_metrics.json",
        report,
    )

    joblib.dump(
        champion,
        MODEL_DIR
        / "logistic_champion.joblib",
    )

    print(
        "\nTest AP:",
        test_metrics[
            "average_precision"
        ],
    )

    print(
        "Test Recall@Top1%:",
        test_metrics[
            "recall_at_top_1pct"
        ],
    )


if __name__ == "__main__":
    main()