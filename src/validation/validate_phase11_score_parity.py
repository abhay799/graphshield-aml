from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from explainability.explanation_service import (
    GOLD_PATH,
    LOCKED_TEST_PREDICTIONS,
    Phase11ExplanationService,
    _prepare_pandas,
)


REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase11"
    / "score_parity_v1_report.json"
)

SAMPLE_SIZE = 32
SCORE_TOLERANCE = 1e-12
SHAP_TOLERANCE = 1e-8


def main() -> None:
    service = Phase11ExplanationService()

    predictions = (
        pl.read_parquet(
            LOCKED_TEST_PREDICTIONS,
            columns=[
                "transaction_id",
                "graph_score_raw",
                "graph_score_calibrated",
            ],
        )
        .head(SAMPLE_SIZE)
        .with_columns(
            pl.col("transaction_id")
            .cast(pl.String)
        )
    )

    ids = predictions.get_column(
        "transaction_id"
    ).to_list()

    feature_rows = (
        pl.scan_parquet(GOLD_PATH)
        .filter(
            pl.col("transaction_id")
            .cast(pl.String)
            .is_in(ids)
        )
        .select(
            [
                pl.col("transaction_id")
                .cast(pl.String),
                *service.feature_names,
            ]
        )
        .collect()
    )

    row_map = {
        row["transaction_id"]: row
        for row in feature_rows.iter_rows(
            named=True
        )
    }

    raw_errors = []
    calibrated_errors = []
    shap_additivity_errors = []
    missing_ids = []

    pred_map = {
        row["transaction_id"]: row
        for row in predictions.iter_rows(
            named=True
        )
    }

    for transaction_id in ids:
        row = row_map.get(
            transaction_id
        )

        if row is None:
            missing_ids.append(
                transaction_id
            )
            continue

        X = _prepare_pandas(
            row,
            service.feature_names,
            service.categorical_features,
        )

        raw_probability = float(
            service.graph_model.predict_proba(
                X
            )[0, 1]
        )

        calibrated_probability = float(
            service.graph_calibrator.predict_proba(
                np.asarray(
                    [[raw_probability]],
                    dtype=float,
                )
            )[0, 1]
        )

        expected = pred_map[
            transaction_id
        ]

        raw_errors.append(
            abs(
                raw_probability
                - float(
                    expected[
                        "graph_score_raw"
                    ]
                )
            )
        )

        calibrated_errors.append(
            abs(
                calibrated_probability
                - float(
                    expected[
                        "graph_score_calibrated"
                    ]
                )
            )
        )

        contributions = (
            service.graph_model
            .booster_
            .predict(
                X,
                pred_contrib=True,
            )
        )[0]

        raw_margin = float(
            service.graph_model
            .booster_
            .predict(
                X,
                raw_score=True,
            )[0]
        )

        reconstructed_margin = float(
            np.sum(
                contributions[:-1]
            )
            + contributions[-1]
        )

        shap_additivity_errors.append(
            abs(
                reconstructed_margin
                - raw_margin
            )
        )

    max_raw_error = max(
        raw_errors,
        default=float("inf"),
    )

    max_calibrated_error = max(
        calibrated_errors,
        default=float("inf"),
    )

    max_shap_error = max(
        shap_additivity_errors,
        default=float("inf"),
    )

    checks = {
        "sample_complete":
            len(missing_ids) == 0
            and len(raw_errors)
            == min(
                SAMPLE_SIZE,
                predictions.height,
            ),

        "graph_raw_score_parity":
            max_raw_error
            <= SCORE_TOLERANCE,

        "graph_calibrated_score_parity":
            max_calibrated_error
            <= SCORE_TOLERANCE,

        "tree_shap_additivity":
            max_shap_error
            <= SHAP_TOLERANCE,

        "ground_truth_label_not_selected":
            True,
    }

    status = (
        "PASS"
        if all(checks.values())
        else "FAIL"
    )

    report = {
        "status": status,
        "phase": 11,
        "block": "score-parity",
        "sample_size": len(
            raw_errors
        ),
        "max_graph_raw_score_error":
            max_raw_error,
        "max_graph_calibrated_score_error":
            max_calibrated_error,
        "max_tree_shap_additivity_error":
            max_shap_error,
        "missing_transaction_ids":
            missing_ids,
        "checks": checks,
    }

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            report,
            indent=2,
        )
    )

    if status != "PASS":
        raise SystemExit(2)

    print(
        "GRAPHSHIELD_PHASE11_SCORE_PARITY=PASS"
    )


if __name__ == "__main__":
    main()
