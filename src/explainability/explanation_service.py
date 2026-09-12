from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PHASE10_CERTIFICATION = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "phase10_certification_v1.json"
)

GRAPH_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "lightgbm_graph_v1.joblib"
)

GRAPH_CALIBRATOR_PATH = (
    PROJECT_ROOT
    / "models"
    / "probability_calibrator_graph_v1.joblib"
)

FUSION_CALIBRATOR_PATH = (
    PROJECT_ROOT
    / "models"
    / "v2"
    / "phase10_fusion_calibrator_v1.joblib"
)

GOLD_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

LOCKED_TEST_PREDICTIONS = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "phase10"
    / "locked_test_predictions_v1.parquet"
)


def _require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def _model_feature_names(model) -> list[str]:
    names = getattr(model, "feature_name_", None)

    if names is None and hasattr(model, "booster_"):
        names = model.booster_.feature_name()

    if names is None:
        raise RuntimeError(
            "Could not determine LightGBM model feature names."
        )

    return list(names)


def _prepare_pandas(
    row: dict[str, Any],
    feature_names: list[str],
    categorical_features: list[str],
) -> pd.DataFrame:
    frame = pd.DataFrame([row]).loc[:, feature_names].copy()
    categoricals = set(categorical_features)

    for name in feature_names:
        if name in categoricals:
            frame[name] = frame[name].astype("category")
        else:
            frame[name] = pd.to_numeric(
                frame[name],
                errors="raise",
            ).astype("float64")

    return frame


def _top_contributions(
    feature_names: list[str],
    values: np.ndarray,
    feature_row: dict[str, Any],
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = []

    for index, name in enumerate(feature_names):
        contribution = float(values[index])

        records.append(
            {
                "feature": name,
                "feature_value": feature_row.get(name),
                "shap_value_raw_margin": contribution,
                "direction": (
                    "raises_risk"
                    if contribution > 0
                    else "lowers_risk"
                    if contribution < 0
                    else "neutral"
                ),
                "absolute_contribution": abs(contribution),
            }
        )

    positive = sorted(
        (
            item
            for item in records
            if item["shap_value_raw_margin"] > 0
        ),
        key=lambda item: item["absolute_contribution"],
        reverse=True,
    )[:limit]

    negative = sorted(
        (
            item
            for item in records
            if item["shap_value_raw_margin"] < 0
        ),
        key=lambda item: item["absolute_contribution"],
        reverse=True,
    )[:limit]

    for items in (positive, negative):
        for rank, item in enumerate(items, start=1):
            item["rank"] = rank
            item.pop("absolute_contribution", None)

    return positive, negative


class Phase11ExplanationService:
    """
    Read-only explanation adapter over the frozen Phase 10 model stack.

    Important:
    - Does not retrain, refit, or mutate certified Phase 10 artifacts.
    - Never selects the ground-truth target for explanation output.
    - TreeSHAP contributions are reported in LightGBM raw-margin space.
    - Fusion/TGN components are exposed as component evidence, not falsely
      represented as SHAP contributions to the calibrated final probability.
    """

    def __init__(self) -> None:
        for path in (
            PHASE10_CERTIFICATION,
            GRAPH_MODEL_PATH,
            GRAPH_CALIBRATOR_PATH,
            GOLD_PATH,
        ):
            _require(path)

        self.certification = json.loads(
            PHASE10_CERTIFICATION.read_text(encoding="utf-8")
        )

        if self.certification.get("status") != "PASS":
            raise RuntimeError(
                "Phase 10 certification is not PASS."
            )

        self.final_candidate = self.certification.get(
            "final_phase10_candidate"
        )

        self.graph_model = joblib.load(GRAPH_MODEL_PATH)
        self.graph_calibration_bundle = joblib.load(
            GRAPH_CALIBRATOR_PATH
        )

        self.feature_names = list(
            self.graph_calibration_bundle["feature_names"]
        )
        self.categorical_features = list(
            self.graph_calibration_bundle["categorical_features"]
        )

        if _model_feature_names(self.graph_model) != self.feature_names:
            raise RuntimeError(
                "Frozen graph model feature schema mismatch."
            )

        self.graph_calibrator = self.graph_calibration_bundle[
            "calibrator"
        ]

        self.fusion_bundle = None

        if FUSION_CALIBRATOR_PATH.exists():
            self.fusion_bundle = joblib.load(
                FUSION_CALIBRATOR_PATH
            )

    def _load_feature_row(
        self,
        transaction_id: str,
    ) -> dict[str, Any]:
        row = (
            pl.scan_parquet(GOLD_PATH)
            .filter(
                pl.col("transaction_id").cast(pl.String)
                == str(transaction_id)
            )
            .select(
                [
                    pl.col("transaction_id").cast(pl.String),
                    pl.col("event_ts"),
                    pl.col("split"),
                    *self.feature_names,
                ]
            )
            .collect()
        )

        if row.height == 0:
            raise KeyError(
                f"Unknown transaction_id: {transaction_id}"
            )

        if row.height != 1:
            raise RuntimeError(
                f"Expected one feature row for {transaction_id}, "
                f"found {row.height}."
            )

        return row.to_dicts()[0]

    def _load_phase10_prediction(
        self,
        transaction_id: str,
    ) -> dict[str, Any] | None:
        if not LOCKED_TEST_PREDICTIONS.exists():
            return None

        row = (
            pl.scan_parquet(LOCKED_TEST_PREDICTIONS)
            .filter(
                pl.col("transaction_id").cast(pl.String)
                == str(transaction_id)
            )
            .select(
                [
                    pl.col("transaction_id").cast(pl.String),
                    pl.col("graph_score_raw"),
                    pl.col("graph_score_calibrated"),
                    pl.col("tgn_risk_score"),
                    pl.col("graph_fixed_ecdf"),
                    pl.col("tgn_fixed_ecdf"),
                    pl.col("fusion_score_raw"),
                    pl.col("fusion_score_calibrated"),
                ]
            )
            .collect()
        )

        if row.height == 0:
            return None

        if row.height != 1:
            raise RuntimeError(
                "Duplicate Phase 10 prediction rows for "
                f"{transaction_id}."
            )

        return row.to_dicts()[0]

    def explain_transaction(
        self,
        transaction_id: str,
        top_k: int = 8,
    ) -> dict[str, Any]:
        if top_k < 1 or top_k > 25:
            raise ValueError(
                "top_k must be between 1 and 25."
            )

        feature_row = self._load_feature_row(
            transaction_id
        )

        X = _prepare_pandas(
            feature_row,
            self.feature_names,
            self.categorical_features,
        )

        graph_score_raw = float(
            self.graph_model.predict_proba(X)[0, 1]
        )

        graph_score_calibrated = float(
            self.graph_calibrator.predict_proba(
                np.asarray([[graph_score_raw]], dtype=float)
            )[0, 1]
        )

        contributions = self.graph_model.booster_.predict(
            X,
            pred_contrib=True,
        )

        if contributions.shape != (
            1,
            len(self.feature_names) + 1,
        ):
            raise RuntimeError(
                "Unexpected TreeSHAP contribution shape."
            )

        shap_values = np.asarray(
            contributions[0, :-1],
            dtype=float,
        )
        expected_value = float(
            contributions[0, -1]
        )

        positive, negative = _top_contributions(
            self.feature_names,
            shap_values,
            feature_row,
            top_k,
        )

        phase10_prediction = self._load_phase10_prediction(
            transaction_id
        )

        temporal_component = None
        fusion_component = None

        if phase10_prediction is not None:
            temporal_component = {
                "tgn_risk_score": float(
                    phase10_prediction["tgn_risk_score"]
                ),
                "interpretation": (
                    "Temporal component score from the frozen "
                    "Phase 10 TGN. This is not a probability "
                    "attribution and is not interpreted with SHAP."
                ),
            }

            fusion_component = {
                "graph_weight": (
                    float(self.fusion_bundle["graph_weight"])
                    if self.fusion_bundle is not None
                    else None
                ),
                "tgn_weight": (
                    float(self.fusion_bundle["tgn_weight"])
                    if self.fusion_bundle is not None
                    else None
                ),
                "graph_fixed_ecdf": float(
                    phase10_prediction["graph_fixed_ecdf"]
                ),
                "tgn_fixed_ecdf": float(
                    phase10_prediction["tgn_fixed_ecdf"]
                ),
                "fusion_score_raw": float(
                    phase10_prediction["fusion_score_raw"]
                ),
                "fusion_score_calibrated": float(
                    phase10_prediction[
                        "fusion_score_calibrated"
                    ]
                ),
            }

        return {
            "transaction_id": str(transaction_id),
            "event_ts": feature_row.get("event_ts"),
            "split": feature_row.get("split"),
            "phase10_final_candidate": self.final_candidate,
            "graph_model": {
                "model_name": "lightgbm_graph",
                "model_artifact": str(GRAPH_MODEL_PATH),
                "score_raw": graph_score_raw,
                "score_calibrated": graph_score_calibrated,
                "tree_shap_space": "raw_margin",
                "tree_shap_expected_value": expected_value,
                "top_risk_raising_features": positive,
                "top_risk_lowering_features": negative,
            },
            "temporal_model": temporal_component,
            "fusion": fusion_component,
            "governance": {
                "mode": "decision_support_only",
                "human_review_required": True,
                "certified_phase10_artifacts": "read_only",
                "ground_truth_label_exposed": False,
                "autonomous_account_blocking": False,
                "autonomous_case_closure": False,
                "autonomous_regulatory_filing": False,
            },
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--transaction-id",
        required=True,
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
    )

    args = parser.parse_args()

    service = Phase11ExplanationService()

    result = service.explain_transaction(
        transaction_id=args.transaction_id,
        top_k=args.top_k,
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
