import json
from pathlib import Path

import joblib
import lightgbm as lgb
import polars as pl


from common import (
    DATA_PATH,
    MODEL_DIR,
    REPORT_DIR,
    TARGET,
    ensure_directories,
    get_feature_columns,
    load_tree_split,
)

from metrics import (
    evaluate_binary,
    save_json,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GRAPH_DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)


GRAPH_FEATURES = [
    "sender_prior_unique_receivers",
    "receiver_prior_unique_senders",

    "pair_prior_tx_count",
    "pair_prior_amount_sum",
    "pair_prior_amount_avg",
    "pair_seconds_since_previous",
    "pair_relationship_age_seconds",

    "pair_share_of_sender_history",
    "pair_share_of_receiver_history",
    "graph_new_pair",
    "graph_established_pair",

    "bank_pair_prior_tx_count",
    "bank_pair_prior_amount_sum",
    "bank_pair_prior_amount_avg",
    "sender_bank_prior_tx_count",
    "bank_pair_share_of_sender_bank_history",

    "reverse_pair_prior_tx_count",
    "reverse_pair_prior_amount_sum",
    "reverse_pair_seconds_since_previous",
    "reciprocal_prior_exists",
    "closes_two_node_cycle",
    "directional_history_balance",

    "sender_prior_unique_senders",
    "receiver_prior_unique_receivers",
    "sender_bridge_degree",
    "receiver_bridge_degree",
]


def load_graph_split(
    split_name,
    features,
    numerical,
    categorical,
    train_fraction=1.0,
):

    lf = (
        pl.scan_parquet(
            GRAPH_DATA_PATH
        )
        .filter(
            pl.col("split")
            == split_name
        )
        .select(
            [
                "transaction_id",
                *features,
                TARGET,
            ]
        )
    )

    if (
        split_name == "train"
        and train_fraction < 1.0
    ):

        threshold = int(
            train_fraction
            * 1_000_000
        )

        lf = lf.filter(
            (
                pl.col("transaction_id")
                .hash(seed=42)
                % 1_000_000
            )
            < threshold
        )

    expressions = []

    for column in numerical:

        expressions.append(
            pl.col(column)
            .cast(pl.Float32)
        )

    for column in categorical:

        expressions.append(
            pl.col(column)
            .cast(pl.String)
            .fill_null("__MISSING__")
        )

    df = (
        lf
        .with_columns(expressions)
        .collect()
        .to_pandas()
    )

    transaction_ids = df.pop(
        "transaction_id"
    )

    y = (
        df.pop(TARGET)
        .astype("int8")
        .to_numpy()
    )

    for column in categorical:
        df[column] = (
            df[column]
            .astype("category")
        )

    return transaction_ids, df, y


def build_lightgbm(
    y_train,
):

    positives = int(
        y_train.sum()
    )

    negatives = (
        len(y_train)
        - positives
    )

    return lgb.LGBMClassifier(
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
            negatives
            / max(positives, 1)
        ),

        random_state=42,
        n_jobs=-1,
        verbosity=-1,
    )


def main():

    ensure_directories()

    print("=" * 90)
    print("GraphShield AML - Graph Incremental Lift Experiment")
    print("=" * 90)

    # ======================================================
    # Read original LightGBM training fraction
    # ======================================================

    with open(
        REPORT_DIR
        / "lightgbm_validation.json",
        "r",
        encoding="utf-8",
    ) as file:

        original_report = json.load(
            file
        )

    train_fraction = float(
        original_report.get(
            "training_fraction",
            1.0,
        )
    )

    print(
        "\nTraining fraction:",
        train_fraction,
    )

    # ======================================================
    # Existing baseline model
    # ======================================================

    baseline_model = joblib.load(
        MODEL_DIR
        / "lightgbm_v1.joblib"
    )

    baseline_features, baseline_num, categorical = (
        get_feature_columns()
    )

    # Validation baseline
    _, X_base_val, y_val = (
        load_tree_split(
            "validation",
            baseline_features,
            baseline_num,
            categorical,
        )
    )

    baseline_val_scores = (
        baseline_model
        .predict_proba(
            X_base_val
        )[:, 1]
    )

    baseline_val_metrics = (
        evaluate_binary(
            y_val,
            baseline_val_scores,
        )
    )

    # Test baseline
    _, X_base_test, y_test = (
        load_tree_split(
            "test",
            baseline_features,
            baseline_num,
            categorical,
        )
    )

    baseline_test_scores = (
        baseline_model
        .predict_proba(
            X_base_test
        )[:, 1]
    )

    baseline_test_metrics = (
        evaluate_binary(
            y_test,
            baseline_test_scores,
        )
    )

    # ======================================================
    # Enhanced feature set
    # ======================================================

    graph_features = (
        baseline_features
        +
        GRAPH_FEATURES
    )

    graph_numerical = (
        baseline_num
        +
        GRAPH_FEATURES
    )

    _, X_train, y_train = (
        load_graph_split(
            "train",
            graph_features,
            graph_numerical,
            categorical,
            train_fraction,
        )
    )

    _, X_val, y_graph_val = (
        load_graph_split(
            "validation",
            graph_features,
            graph_numerical,
            categorical,
        )
    )

    print(
        f"\nGraph train rows: "
        f"{len(y_train):,}"
    )

    graph_model = build_lightgbm(
        y_train
    )

    graph_model.fit(
        X_train,
        y_train,

        categorical_feature=categorical,

        eval_set=[
            (
                X_val,
                y_graph_val,
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

    graph_val_scores = (
        graph_model
        .predict_proba(
            X_val
        )[:, 1]
    )

    graph_val_metrics = (
        evaluate_binary(
            y_graph_val,
            graph_val_scores,
        )
    )

    # ======================================================
    # Test graph model
    # ======================================================

    ids_test, X_test, y_graph_test = (
        load_graph_split(
            "test",
            graph_features,
            graph_numerical,
            categorical,
        )
    )

    graph_test_scores = (
        graph_model
        .predict_proba(
            X_test
        )[:, 1]
    )

    graph_test_metrics = (
        evaluate_binary(
            y_graph_test,
            graph_test_scores,
        )
    )

    # ======================================================
    # Save
    # ======================================================

    joblib.dump(
        graph_model,
        MODEL_DIR
        / "lightgbm_graph_v1.joblib",
    )

    report = {
        "training_fraction": (
            train_fraction
        ),

        "baseline_validation": (
            baseline_val_metrics
        ),

        "graph_validation": (
            graph_val_metrics
        ),

        "baseline_test": (
            baseline_test_metrics
        ),

        "graph_test": (
            graph_test_metrics
        ),

        "graph_features": (
            GRAPH_FEATURES
        ),
    }

    save_json(
        REPORT_DIR
        / "graph_ablation_metrics.json",
        report,
    )

    pl.DataFrame(
        {
            "transaction_id":
                ids_test.to_numpy(),

            "is_laundering":
                y_graph_test,

            "baseline_score":
                baseline_test_scores,

            "graph_score":
                graph_test_scores,
        }
    ).write_parquet(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "modeling"
        / "graph_ablation_test_predictions.parquet",
        compression="zstd",
    )

    print("\n--- VALIDATION ---")

    print(
        "Baseline AP:",
        baseline_val_metrics[
            "average_precision"
        ],
    )

    print(
        "Graph AP:",
        graph_val_metrics[
            "average_precision"
        ],
    )

    print(
        "Baseline Recall@1%:",
        baseline_val_metrics[
            "recall_at_top_1pct"
        ],
    )

    print(
        "Graph Recall@1%:",
        graph_val_metrics[
            "recall_at_top_1pct"
        ],
    )

    print("\nSaved graph ablation report.")


if __name__ == "__main__":
    main()