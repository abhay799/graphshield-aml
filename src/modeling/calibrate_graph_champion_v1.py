from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELING_DIR = PROJECT_ROOT / "src" / "modeling"

if str(MODELING_DIR) not in sys.path:
    sys.path.insert(0, str(MODELING_DIR))

from common import MODEL_DIR, get_feature_columns
from train_graph_ablation import GRAPH_FEATURES, load_graph_split


MODEL_PATH = MODEL_DIR / "lightgbm_graph_v1.joblib"

OUTPUT_PATH = (
    MODEL_DIR
    / "probability_calibrator_graph_v1.joblib"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "graph_calibration_v1_report.json"
)

CALIBRATION_VERSION = "platt_graph_v1"


def logit(probability):
    probability = np.clip(
        probability,
        1e-6,
        1 - 1e-6,
    )

    return np.log(
        probability / (1 - probability)
    )


def main():

    print("=" * 88)
    print("GraphShield AML - Phase 10 - Graph Champion Calibration v1")
    print("=" * 88)

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Graph champion missing: {MODEL_PATH}"
        )

    baseline_features, baseline_numerical, categorical = (
        get_feature_columns()
    )

    features = (
        baseline_features
        + GRAPH_FEATURES
    )

    numerical = (
        baseline_numerical
        + GRAPH_FEATURES
    )

    print(f"FEATURE_COUNT={len(features)}")
    print("CALIBRATION_SPLIT=validation")
    print("TEST_USED_FOR_FIT=FALSE")

    _, X_val, y_val = load_graph_split(
        "validation",
        features,
        numerical,
        categorical,
    )

    model = joblib.load(
        MODEL_PATH
    )

    model_features = list(
        model.feature_name_
    )

    if model_features != features:
        raise RuntimeError(
            "Frozen graph-model feature schema does not "
            "match the current training contract."
        )

    raw_scores = (
        model
        .predict_proba(X_val)[:, 1]
    )

    calibrator = LogisticRegression(
        C=1_000_000,
        max_iter=1000,
        solver="lbfgs",
    )

    calibrator.fit(
        logit(raw_scores).reshape(-1, 1),
        y_val,
    )

    calibrated_scores = (
        calibrator.predict_proba(
            logit(raw_scores).reshape(-1, 1)
        )[:, 1]
    )

    raw_brier = float(
        brier_score_loss(
            y_val,
            raw_scores,
        )
    )

    calibrated_brier = float(
        brier_score_loss(
            y_val,
            calibrated_scores,
        )
    )

    artifact = {
        "champion": "lightgbm_graph",
        "model_artifact": "lightgbm_graph_v1.joblib",
        "calibration_version": CALIBRATION_VERSION,
        "method": "platt_logit",
        "fit_split": "validation",
        "test_used_for_fit": False,
        "feature_names": features,
        "categorical_features": categorical,
        "calibrator": calibrator,
    }

    joblib.dump(
        artifact,
        OUTPUT_PATH,
    )

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "status": "PASS",
        "phase": 10,
        "block": "A1",
        "champion": "lightgbm_graph",
        "model_artifact": MODEL_PATH.name,
        "calibration_artifact": OUTPUT_PATH.name,
        "calibration_version": CALIBRATION_VERSION,
        "method": "platt_logit",
        "fit_split": "validation",
        "validation_rows": int(len(y_val)),
        "feature_count": len(features),
        "test_used_for_fit": False,
        "labels_used_only_for_validation_calibration": True,
        "raw_validation_brier": raw_brier,
        "calibrated_validation_brier": calibrated_brier,
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"VALIDATION_ROWS={len(y_val):,}"
    )

    print(
        f"RAW_BRIER={raw_brier:.12f}"
    )

    print(
        f"CALIBRATED_BRIER={calibrated_brier:.12f}"
    )

    print(
        f"ARTIFACT={OUTPUT_PATH}"
    )

    print(
        f"REPORT={REPORT_PATH}"
    )

    print("TEST_USED_FOR_FIT=FALSE")
    print("GRAPHSHIELD_PHASE10_BLOCK_A1=PASS")


if __name__ == "__main__":
    main()