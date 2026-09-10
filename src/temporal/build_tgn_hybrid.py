from pathlib import Path

import json

import joblib
import numpy as np
import pandas as pd
import polars as pl


from tgn_common import (
    PROJECT_ROOT,
    evaluate_scores,
)


GRAPH_DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

GRAPH_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "lightgbm_graph_v1.joblib"
)

TGN_VAL_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
    / "tgn_validation_predictions.parquet"
)

TGN_TEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
    / "tgn_test_predictions.parquet"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
    / "tgn_hybrid_fusion.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
    / "tgn_hybrid_test_predictions.parquet"
)


CATEGORICAL = [
    "payment_format",
    "payment_currency",
    "receiving_currency",
]


def load_graph_scores(
    model,
    split_name,
):

    feature_names = (
        list(
            model.feature_name_
        )
    )

    df = (
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
                *feature_names,
                "is_laundering",
            ]
        )
        .collect()
        .to_pandas()
    )

    transaction_ids = (
        df[
            "transaction_id"
        ].copy()
    )

    y = (
        df[
            "is_laundering"
        ]
        .astype("int8")
        .to_numpy()
    )

    X = df[
        feature_names
    ].copy()

    for column in CATEGORICAL:

        if column in X.columns:

            X[column] = (
                X[column]
                .astype("category")
            )

    scores = (
        model.predict_proba(
            X
        )[:, 1]
    )

    return pd.DataFrame(
        {
            "transaction_id":
                transaction_ids,

            "is_laundering":
                y,

            "graph_score":
                scores,
        }
    )


def percentile_rank(
    values,
):

    return (
        pd.Series(
            values
        )
        .rank(
            method="average",
            pct=True,
        )
        .to_numpy()
    )


def combine(
    graph_df,
    tgn_path,
):

    tgn = (
        pl.read_parquet(
            tgn_path
        )
        .to_pandas()
    )

    tgn = tgn[
        [
            "transaction_id",
            "tgn_risk_score",
        ]
    ]

    merged = graph_df.merge(
        tgn,
        on="transaction_id",
        how="inner",
        validate="one_to_one",
    )

    merged[
        "graph_rank"
    ] = percentile_rank(
        merged[
            "graph_score"
        ].to_numpy()
    )

    merged[
        "tgn_rank"
    ] = percentile_rank(
        merged[
            "tgn_risk_score"
        ].to_numpy()
    )

    return merged


def main():

    print("=" * 90)
    print("GraphShield AML - Graph + TGN Hybrid")
    print("=" * 90)

    model = joblib.load(
        GRAPH_MODEL_PATH
    )

    print(
        "\nGenerating graph-model validation scores..."
    )

    graph_val = load_graph_scores(
        model,
        "validation",
    )

    print(
        "Generating graph-model test scores..."
    )

    graph_test = load_graph_scores(
        model,
        "test",
    )

    validation = combine(
        graph_val,
        TGN_VAL_PATH,
    )

    test = combine(
        graph_test,
        TGN_TEST_PATH,
    )

    print(
        f"\nValidation rows in fusion: "
        f"{len(validation):,}"
    )

    # ======================================================
    # Select fusion weight using VALIDATION only
    # ======================================================

    candidates = []

    for alpha in np.linspace(
        0.0,
        1.0,
        21,
    ):

        score = (
            alpha
            * validation[
                "graph_rank"
            ].to_numpy()
            +
            (1.0 - alpha)
            * validation[
                "tgn_rank"
            ].to_numpy()
        )

        metrics = evaluate_scores(
            validation[
                "is_laundering"
            ].to_numpy(),
            score,
        )

        candidates.append(
            {
                "alpha_graph":
                    float(alpha),

                "alpha_tgn":
                    float(
                        1.0 - alpha
                    ),

                "metrics":
                    metrics,
            }
        )

    best = max(
        candidates,
        key=lambda item: (
            item[
                "metrics"
            ][
                "average_precision"
            ],

            item[
                "metrics"
            ][
                "recall_at_top_1pct"
            ],
        ),
    )

    alpha = best[
        "alpha_graph"
    ]

    print(
        "\nSelected validation fusion:"
    )

    print(
        f"Graph weight: {alpha:.2f}"
    )

    print(
        f"TGN weight:   "
        f"{1-alpha:.2f}"
    )

    # ======================================================
    # Validation components
    # ======================================================

    graph_val_metrics = (
        evaluate_scores(
            validation[
                "is_laundering"
            ].to_numpy(),

            validation[
                "graph_score"
            ].to_numpy(),
        )
    )

    tgn_val_metrics = (
        evaluate_scores(
            validation[
                "is_laundering"
            ].to_numpy(),

            validation[
                "tgn_risk_score"
            ].to_numpy(),
        )
    )

    hybrid_val_metrics = (
        best[
            "metrics"
        ]
    )

    # ======================================================
    # Untouched TEST with frozen alpha
    # ======================================================

    test[
        "hybrid_rank_score"
    ] = (
        alpha
        * test[
            "graph_rank"
        ].to_numpy()
        +
        (1.0 - alpha)
        * test[
            "tgn_rank"
        ].to_numpy()
    )

    graph_test_metrics = (
        evaluate_scores(
            test[
                "is_laundering"
            ].to_numpy(),

            test[
                "graph_score"
            ].to_numpy(),
        )
    )

    tgn_test_metrics = (
        evaluate_scores(
            test[
                "is_laundering"
            ].to_numpy(),

            test[
                "tgn_risk_score"
            ].to_numpy(),
        )
    )

    hybrid_test_metrics = (
        evaluate_scores(
            test[
                "is_laundering"
            ].to_numpy(),

            test[
                "hybrid_rank_score"
            ].to_numpy(),
        )
    )

    print(
        "\n--- VALIDATION AP ---"
    )

    print(
        "Graph:",
        graph_val_metrics[
            "average_precision"
        ],
    )

    print(
        "TGN:",
        tgn_val_metrics[
            "average_precision"
        ],
    )

    print(
        "Hybrid:",
        hybrid_val_metrics[
            "average_precision"
        ],
    )

    print(
        "\n--- TEST AP ---"
    )

    print(
        "Graph:",
        graph_test_metrics[
            "average_precision"
        ],
    )

    print(
        "TGN:",
        tgn_test_metrics[
            "average_precision"
        ],
    )

    print(
        "Hybrid:",
        hybrid_test_metrics[
            "average_precision"
        ],
    )

    report = {
        "selection_dataset":
            "validation",

        "fusion_method":
            "percentile-rank weighted fusion",

        "alpha_graph":
            alpha,

        "alpha_tgn":
            1.0 - alpha,

        "validation_candidates":
            candidates,

        "validation_graph":
            graph_val_metrics,

        "validation_tgn":
            tgn_val_metrics,

        "validation_hybrid":
            hybrid_val_metrics,

        "test_graph":
            graph_test_metrics,

        "test_tgn":
            tgn_test_metrics,

        "test_hybrid":
            hybrid_test_metrics,
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        REPORT_PATH,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
        )

    pl.from_pandas(
        test[
            [
                "transaction_id",
                "is_laundering",
                "graph_score",
                "tgn_risk_score",
                "hybrid_rank_score",
            ]
        ]
    ).write_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(REPORT_PATH)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()