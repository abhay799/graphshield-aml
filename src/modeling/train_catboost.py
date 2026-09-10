import os

import numpy as np
import polars as pl

from catboost import (
    CatBoostClassifier,
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


TRAIN_FRACTION = float(
    os.getenv(
        "GS_TREE_TRAIN_FRACTION",
        "1.0",
    )
)


def make_catboost_ready(
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
    print("GraphShield AML - CatBoost")
    print("=" * 80)

    features, numerical, categorical = (
        get_feature_columns()
    )

    ids_train, X_train, y_train = (
        load_tree_split(
            "train",
            features,
            numerical,
            categorical,
            TRAIN_FRACTION,
        )
    )

    ids_val, X_val, y_val = (
        load_tree_split(
            "validation",
            features,
            numerical,
            categorical,
        )
    )

    X_train = make_catboost_ready(
        X_train,
        categorical,
    )

    X_val = make_catboost_ready(
        X_val,
        categorical,
    )

    model = CatBoostClassifier(
        iterations=1500,

        depth=8,

        learning_rate=0.05,

        loss_function="Logloss",

        eval_metric="PRAUC:type=Classic",

        auto_class_weights="Balanced",

        random_seed=42,

        thread_count=-1,

        verbose=100,

        allow_writing_files=False,
    )

    model.fit(
        X_train,
        y_train,

        cat_features=(
            categorical
        ),

        eval_set=(
            X_val,
            y_val,
        ),

        use_best_model=True,

        early_stopping_rounds=100,
    )

    val_probability = (
        model.predict_proba(
            X_val
        )[:, 1]
    )

    metrics = evaluate_binary(
        y_val,
        val_probability,
    )

    print(
        "\nValidation AP:",
        metrics[
            "average_precision"
        ],
    )

    print(
        "Validation Recall@Top1%:",
        metrics[
            "recall_at_top_1pct"
        ],
    )

    model.save_model(
        str(
            MODEL_DIR
            / "catboost_v1.cbm"
        )
    )

    save_json(
        REPORT_DIR
        / "catboost_validation.json",
        {
            "model": "catboost",
            "training_fraction": (
                TRAIN_FRACTION
            ),
            **metrics,
        },
    )

    pl.DataFrame(
        {
            "transaction_id": (
                ids_val.to_numpy()
            ),

            "is_laundering": (
                y_val
            ),

            "risk_score": (
                val_probability
            ),
        }
    ).write_parquet(
        PREDICTION_DIR
        / "catboost_validation.parquet",
        compression="zstd",
    )

    print(
        "\nSaved CatBoost challenger."
    )


if __name__ == "__main__":
    main()