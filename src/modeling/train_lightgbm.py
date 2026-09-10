import os

import joblib
import lightgbm as lgb
import numpy as np
import polars as pl

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


def main():

    ensure_directories()

    print("=" * 80)
    print("GraphShield AML - LightGBM")
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

    positives = int(
        y_train.sum()
    )

    negatives = int(
        len(y_train)
        - positives
    )

    scale_pos_weight = (
        negatives
        / max(
            positives,
            1,
        )
    )

    print(
        f"\nTrain rows: "
        f"{len(y_train):,}"
    )

    print(
        f"Positive rows: "
        f"{positives:,}"
    )

    print(
        f"scale_pos_weight: "
        f"{scale_pos_weight:.2f}"
    )

    model = lgb.LGBMClassifier(
        objective="binary",

        n_estimators=2000,
        learning_rate=0.03,

        num_leaves=31,
        max_depth=-1,

        min_child_samples=50,

        subsample=0.80,
        colsample_bytree=0.80,

        reg_alpha=0.0,
        reg_lambda=1.0,

        scale_pos_weight=(
            scale_pos_weight
        ),

        random_state=42,

        n_jobs=-1,

        verbosity=-1,
    )

    model.fit(
        X_train,
        y_train,

        categorical_feature=(
            categorical
        ),

        eval_set=[
            (
                X_val,
                y_val,
            )
        ],

        eval_metric="average_precision",

        callbacks=[
            lgb.early_stopping(
                stopping_rounds=100
            ),

            lgb.log_evaluation(
                period=50
            ),
        ],
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

    joblib.dump(
        model,
        MODEL_DIR
        / "lightgbm_v1.joblib",
    )

    save_json(
        REPORT_DIR
        / "lightgbm_validation.json",
        {
            "model": "lightgbm",
            "training_fraction": (
                TRAIN_FRACTION
            ),
            **metrics,
        },
    )

    predictions = pl.DataFrame(
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
    )

    predictions.write_parquet(
        PREDICTION_DIR
        / "lightgbm_validation.parquet",
        compression="zstd",
    )

    print(
        "\nSaved LightGBM model."
    )


if __name__ == "__main__":
    main()