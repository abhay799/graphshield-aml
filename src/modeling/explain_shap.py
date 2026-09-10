import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from catboost import (
    CatBoostClassifier,
    Pool,
)

from common import (
    MODEL_DIR,
    REPORT_DIR,
    ensure_directories,
    get_feature_columns,
    load_tree_split,
)


SAMPLE_SIZE = 20_000


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
    print("GraphShield AML - TreeSHAP Explanations")
    print("=" * 80)

    champion_name = (
        MODEL_DIR
        / "champion_name.txt"
    ).read_text(
        encoding="utf-8"
    ).strip()

    print(
        "\nChampion:",
        champion_name,
    )

    features, numerical, categorical = (
        get_feature_columns()
    )

    ids, X_test, y_test = (
        load_tree_split(
            "test",
            features,
            numerical,
            categorical,
        )
    )

    # ======================================================
    # Deterministic test sample
    # ======================================================

    rng = np.random.default_rng(42)

    sample_size = min(
        SAMPLE_SIZE,
        len(X_test),
    )

    indices = rng.choice(
        len(X_test),
        size=sample_size,
        replace=False,
    )

    X_sample = (
        X_test.iloc[
            indices
        ]
        .copy()
    )

    ids_sample = (
        ids.iloc[
            indices
        ]
        .reset_index(
            drop=True
        )
    )

    # ======================================================
    # Native TreeSHAP
    # ======================================================

    if champion_name == "lightgbm":

        model = joblib.load(
            MODEL_DIR
            / "lightgbm_v1.joblib"
        )

        contributions = (
            model.booster_
            .predict(
                X_sample,
                pred_contrib=True,
            )
        )

        # Last column = expected/base value
        shap_values = (
            contributions[:, :-1]
        )

        risk_scores = (
            model.predict_proba(
                X_sample
            )[:, 1]
        )

    else:

        model = CatBoostClassifier()

        model.load_model(
            str(
                MODEL_DIR
                / "catboost_v1.cbm"
            )
        )

        X_sample = catboost_ready(
            X_sample,
            categorical,
        )

        pool = Pool(
            X_sample,
            cat_features=(
                categorical
            ),
        )

        contributions = (
            model.get_feature_importance(
                pool,
                type="ShapValues",
            )
        )

        shap_values = (
            contributions[:, :-1]
        )

        risk_scores = (
            model.predict_proba(
                X_sample
            )[:, 1]
        )

    # ======================================================
    # Global feature importance
    # ======================================================

    mean_absolute_shap = (
        np.abs(
            shap_values
        )
        .mean(
            axis=0
        )
    )

    global_importance = (
        pd.DataFrame(
            {
                "feature": (
                    X_sample.columns
                ),

                "mean_abs_shap": (
                    mean_absolute_shap
                ),
            }
        )
        .sort_values(
            "mean_abs_shap",
            ascending=False,
        )
    )

    global_importance.to_csv(
        REPORT_DIR
        / "shap_global_importance.csv",
        index=False,
    )

    print(
        "\nTop SHAP features:"
    )

    print(
        global_importance
        .head(15)
        .to_string(
            index=False
        )
    )

    # ======================================================
    # Plot top 20
    # ======================================================

    plot_data = (
        global_importance
        .head(20)
        .sort_values(
            "mean_abs_shap",
            ascending=True,
        )
    )

    plt.figure(
        figsize=(10, 8)
    )

    plt.barh(
        plot_data["feature"],
        plot_data[
            "mean_abs_shap"
        ],
    )

    plt.xlabel(
        "Mean |SHAP value|"
    )

    plt.ylabel(
        "Feature"
    )

    plt.title(
        "GraphShield AML - Global TreeSHAP Importance"
    )

    plt.tight_layout()

    plt.savefig(
        REPORT_DIR
        / "shap_global_importance.png",
        dpi=200,
    )

    plt.close()

    # ======================================================
    # Local explanations for highest-risk sample rows
    # ======================================================

    highest_risk = np.argsort(
        risk_scores
    )[::-1][:20]

    local_records = []

    for row_index in highest_risk:

        row_shap = (
            shap_values[
                row_index
            ]
        )

        strongest = np.argsort(
            np.abs(
                row_shap
            )
        )[::-1][:5]

        for rank, feature_index in enumerate(
            strongest,
            start=1,
        ):

            feature = (
                X_sample.columns[
                    feature_index
                ]
            )

            local_records.append(
                {
                    "transaction_id": (
                        ids_sample.iloc[
                            row_index
                        ]
                    ),

                    "risk_score": float(
                        risk_scores[
                            row_index
                        ]
                    ),

                    "rank": rank,

                    "feature": feature,

                    "feature_value": str(
                        X_sample.iloc[
                            row_index,
                            feature_index,
                        ]
                    ),

                    "shap_value": float(
                        row_shap[
                            feature_index
                        ]
                    ),
                }
            )

    pd.DataFrame(
        local_records
    ).to_csv(
        REPORT_DIR
        / "shap_local_high_risk.csv",
        index=False,
    )

    print(
        "\nSaved global and local SHAP explanations."
    )


if __name__ == "__main__":
    main()