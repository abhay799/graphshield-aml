from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import polars as pl
import pyarrow.parquet as pq
import torch
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


ROOT = Path(__file__).resolve().parents[2]
TEMPORAL_DIR = ROOT / "src" / "temporal"
if str(TEMPORAL_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPORAL_DIR))

from tgn_common import (
    build_system,
    evaluate_split,
    load_event_bundle,
    load_parameter_state,
    replay_split,
    reset_system,
)


GOLD = (
    ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

GRAPH_MODEL = ROOT / "models" / "lightgbm_graph_v1.joblib"
GRAPH_CAL = ROOT / "models" / "probability_calibrator_graph_v1.joblib"

TGN_CHECKPOINT = (
    ROOT
    / "models"
    / "v2"
    / "tgn_phase10c"
    / "tgn_risk.pt"
)

FUSION_CAL = (
    ROOT
    / "models"
    / "v2"
    / "phase10_fusion_calibrator_v1.joblib"
)

FUSION_CAL_REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "fusion_calibration_v1_report.json"
)

TEST_FEATURE_SLICE = (
    ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "phase10"
    / "graph_test_feature_slice_v1.parquet"
)

TEST_PREDICTIONS = (
    ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "phase10"
    / "locked_test_predictions_v1.parquet"
)

REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "locked_test_evaluation_v1.json"
)

TRAIN_PREFIX = 750_000
BATCH_SIZE = 50_000


def top_fraction_metrics(
    y: np.ndarray,
    scores: np.ndarray,
    fraction: float = 0.01,
) -> dict:
    n = len(y)
    k = max(1, int(np.ceil(n * fraction)))
    order = np.argsort(-scores, kind="mergesort")
    top = order[:k]

    positives = int(y.sum())
    tp = int(y[top].sum())

    precision = tp / k
    recall = tp / positives if positives else 0.0
    prevalence = positives / n if n else 0.0

    return {
        "k": k,
        "precision_at_top_1pct": precision,
        "recall_at_top_1pct": recall,
        "lift_at_top_1pct": (
            precision / prevalence if prevalence > 0 else 0.0
        ),
    }


def ece_10(y: np.ndarray, p: np.ndarray) -> float:
    edges = np.linspace(0.0, 1.0, 11)
    total = len(y)
    out = 0.0

    for i in range(10):
        lo = edges[i]
        hi = edges[i + 1]

        if i == 9:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)

        n = int(mask.sum())
        if n == 0:
            continue

        out += (
            n / total
        ) * abs(
            float(y[mask].mean())
            - float(p[mask].mean())
        )

    return float(out)


def evaluate(
    y: np.ndarray,
    scores: np.ndarray,
    probability: bool = False,
) -> dict:
    result = {
        "rows": int(len(y)),
        "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "average_precision": float(
            average_precision_score(y, scores)
        ),
    }

    try:
        result["roc_auc"] = float(
            roc_auc_score(y, scores)
        )
    except ValueError:
        result["roc_auc"] = None

    result.update(
        top_fraction_metrics(y, scores)
    )

    if probability:
        result["brier_score"] = float(
            brier_score_loss(y, scores)
        )
        result["ece_10_bins"] = ece_10(
            y,
            scores,
        )

    return result


def fixed_ecdf(
    values: np.ndarray,
    sorted_reference: np.ndarray,
) -> np.ndarray:
    return (
        np.searchsorted(
            sorted_reference,
            np.asarray(values, dtype=float),
            side="right",
        )
        / float(len(sorted_reference))
    )


def model_feature_names(model) -> list[str]:
    names = getattr(
        model,
        "feature_name_",
        None,
    )

    if names is None and hasattr(model, "booster_"):
        names = model.booster_.feature_name()

    if names is None:
        raise RuntimeError(
            "Could not read LightGBM feature names."
        )

    return list(names)


def prepare_pandas(
    frame: pd.DataFrame,
    feature_names: list[str],
    categorical_features: list[str],
) -> pd.DataFrame:
    out = frame.loc[:, feature_names].copy()
    cats = set(categorical_features)

    for name in feature_names:
        if name in cats:
            out[name] = out[name].astype(
                "category"
            )
        else:
            out[name] = pd.to_numeric(
                out[name],
                errors="raise",
            ).astype("float64")

    return out


def build_and_score_graph_test(
    model,
    feature_names: list[str],
    categorical_features: list[str],
) -> pl.DataFrame:
    print(
        "BUILD_LOCKED_TEST_FEATURE_SLICE=START"
    )

    (
        pl.scan_parquet(GOLD)
        .filter(pl.col("split") == "test")
        .select(
            [
                pl.col(
                    "transaction_id"
                ).cast(pl.String),
                pl.col(
                    "is_laundering"
                ).cast(pl.Int8),
                *feature_names,
            ]
        )
        .sink_parquet(
            TEST_FEATURE_SLICE,
            compression="zstd",
        )
    )

    print(
        "BUILD_LOCKED_TEST_FEATURE_SLICE=PASS"
    )

    parquet = pq.ParquetFile(
        TEST_FEATURE_SLICE
    )

    txids: list[str] = []
    labels: list[int] = []
    graph_raw: list[float] = []

    done = 0

    print(
        "GRAPH_LOCKED_TEST_SCORING=START"
    )

    for batch in parquet.iter_batches(
        batch_size=BATCH_SIZE
    ):
        df = batch.to_pandas()

        X = prepare_pandas(
            df,
            feature_names,
            categorical_features,
        )

        pred = np.asarray(
            model.predict_proba(X)[:, 1],
            dtype=float,
        )

        txids.extend(
            df["transaction_id"]
            .astype(str)
            .tolist()
        )
        labels.extend(
            df["is_laundering"]
            .astype(int)
            .tolist()
        )
        graph_raw.extend(
            pred.tolist()
        )

        done += len(df)

        if done % 100_000 < BATCH_SIZE:
            print(
                f"GRAPH_TEST_ROWS_SCORED="
                f"{done:,}"
            )

    print(
        "GRAPH_LOCKED_TEST_SCORING=PASS"
    )

    return pl.DataFrame(
        {
            "transaction_id": txids,
            "is_laundering": labels,
            "graph_score_raw": graph_raw,
        }
    )


def score_tgn_locked_test() -> pl.DataFrame:
    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print(f"TGN_DEVICE={device}")
    print("TGN_RETRAINING=FALSE")
    print(
        f"TGN_TRAIN_HISTORY_PREFIX="
        f"{TRAIN_PREFIX:,}"
    )
    print(
        "TGN_VALIDATION_REPLAY_BEFORE_TEST=TRUE"
    )

    checkpoint = torch.load(
        TGN_CHECKPOINT,
        map_location=device,
    )

    config = checkpoint["config"]

    print(
        "LOADING_TEMPORAL_BUNDLE=START"
    )

    bundle = load_event_bundle(
        max_train_events=TRAIN_PREFIX,
        max_val_events=None,
        max_test_events=None,
    )

    print(
        "LOADING_TEMPORAL_BUNDLE=PASS"
    )

    system = build_system(
        bundle,
        device,
        memory_dim=int(
            config["memory_dim"]
        ),
        time_dim=int(
            config["time_dim"]
        ),
        embedding_dim=int(
            config["embedding_dim"]
        ),
        neighbor_size=int(
            config["neighbor_size"]
        ),
    )

    load_parameter_state(
        system.memory,
        checkpoint["memory_parameters"],
    )
    system.gnn.load_state_dict(
        checkpoint["gnn_state"]
    )
    system.classifier.load_state_dict(
        checkpoint["classifier_state"]
    )

    reset_system(system)

    system.memory.eval()
    system.gnn.eval()
    system.classifier.eval()

    print(
        "REPLAYING_FROZEN_TRAIN_HISTORY=START"
    )

    replay_split(
        bundle,
        system,
        device,
        "train",
    )

    print(
        "REPLAYING_FROZEN_TRAIN_HISTORY=PASS"
    )

    # Validation is a real temporal continuation. It is scored here
    # only to advance TGN memory before test. No tuning occurs.
    print(
        "ADVANCING_THROUGH_FULL_VALIDATION=START"
    )

    _y_val, _val_scores = evaluate_split(
        bundle,
        system,
        device,
        "validation",
    )

    print(
        "ADVANCING_THROUGH_FULL_VALIDATION=PASS"
    )

    print(
        "TGN_LOCKED_TEST_SCORING=START"
    )

    y_test, tgn_scores = evaluate_split(
        bundle,
        system,
        device,
        "test",
    )

    print(
        "TGN_LOCKED_TEST_SCORING=PASS"
    )

    return pl.DataFrame(
        {
            "transaction_id":
                bundle.ids["test"],
            "tgn_label":
                y_test,
            "tgn_risk_score":
                tgn_scores,
        }
    )


def main() -> None:
    # One-time guard. A completed locked-test report must never be
    # silently overwritten and then used for further tuning.
    if REPORT.exists():
        raise RuntimeError(
            "LOCKED TEST ALREADY EVALUATED for Phase 10. "
            f"Existing report: {REPORT}"
        )

    required = [
        GOLD,
        GRAPH_MODEL,
        GRAPH_CAL,
        TGN_CHECKPOINT,
        FUSION_CAL,
        FUSION_CAL_REPORT,
    ]

    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

    cal_report = json.loads(
        FUSION_CAL_REPORT.read_text(
            encoding="utf-8"
        )
    )

    if (
        cal_report.get("status") != "PASS"
        or cal_report.get(
            "test_used_for_selection"
        ) is not False
        or cal_report.get(
            "test_used_for_calibration_fit"
        ) is not False
    ):
        raise RuntimeError(
            "Frozen validation-only calibration "
            "contract is not certified."
        )

    graph_model = joblib.load(
        GRAPH_MODEL
    )
    graph_cal_bundle = joblib.load(
        GRAPH_CAL
    )
    fusion_bundle = joblib.load(
        FUSION_CAL
    )

    feature_names = list(
        graph_cal_bundle[
            "feature_names"
        ]
    )
    categorical_features = list(
        graph_cal_bundle[
            "categorical_features"
        ]
    )

    if (
        model_feature_names(
            graph_model
        )
        != feature_names
    ):
        raise RuntimeError(
            "Graph model feature schema mismatch."
        )

    graph_calibrator = (
        graph_cal_bundle[
            "calibrator"
        ]
    )

    fusion_calibrator = (
        fusion_bundle[
            "calibrator"
        ]
    )

    graph_weight = float(
        fusion_bundle[
            "graph_weight"
        ]
    )
    tgn_weight = float(
        fusion_bundle[
            "tgn_weight"
        ]
    )

    if (
        abs(graph_weight - 0.99)
        > 1e-12
        or abs(tgn_weight - 0.01)
        > 1e-12
    ):
        raise RuntimeError(
            "Frozen fusion weights changed."
        )

    graph_ref = np.asarray(
        fusion_bundle[
            "graph_reference_sorted"
        ],
        dtype=float,
    )
    tgn_ref = np.asarray(
        fusion_bundle[
            "tgn_reference_sorted"
        ],
        dtype=float,
    )

    print("=" * 96)
    print(
        "GraphShield AML - Phase 10D "
        "- ONE-TIME LOCKED TEST"
    )
    print("=" * 96)
    print(
        f"FROZEN_GRAPH_WEIGHT="
        f"{graph_weight:.2f}"
    )
    print(
        f"FROZEN_TGN_WEIGHT="
        f"{tgn_weight:.2f}"
    )
    print(
        "MODEL_OR_WEIGHT_TUNING_AFTER_TEST=FALSE"
    )
    print(
        "CALIBRATOR_REFIT_ON_TEST=FALSE"
    )
    print(
        "TGN_RETRAINING=FALSE"
    )

    # From this point onward, the locked test is being evaluated.
    graph = build_and_score_graph_test(
        graph_model,
        feature_names,
        categorical_features,
    )

    tgn = score_tgn_locked_test().with_columns(
        pl.col(
            "transaction_id"
        ).cast(pl.String),
        pl.col(
            "tgn_label"
        ).cast(pl.Int8),
        pl.col(
            "tgn_risk_score"
        ).cast(pl.Float64),
    )

    aligned = graph.join(
        tgn,
        on="transaction_id",
        how="inner",
        validate="1:1",
    )

    if (
        aligned.height
        != graph.height
        or aligned.height
        != tgn.height
    ):
        raise RuntimeError(
            "Locked-test graph/TGN alignment failed: "
            f"GRAPH={graph.height:,}, "
            f"TGN={tgn.height:,}, "
            f"JOIN={aligned.height:,}"
        )

    label_mismatches = (
        aligned.filter(
            pl.col(
                "is_laundering"
            )
            != pl.col(
                "tgn_label"
            )
        ).height
    )

    if label_mismatches:
        raise RuntimeError(
            "Locked-test label mismatch: "
            f"{label_mismatches}"
        )

    y = (
        aligned.get_column(
            "is_laundering"
        )
        .to_numpy()
        .astype(int)
    )

    graph_raw = (
        aligned.get_column(
            "graph_score_raw"
        )
        .to_numpy()
    )

    tgn_raw = (
        aligned.get_column(
            "tgn_risk_score"
        )
        .to_numpy()
    )

    graph_calibrated = (
        graph_calibrator
        .predict_proba(
            graph_raw.reshape(
                -1,
                1,
            )
        )[:, 1]
    )

    graph_q = fixed_ecdf(
        graph_raw,
        graph_ref,
    )
    tgn_q = fixed_ecdf(
        tgn_raw,
        tgn_ref,
    )

    fusion_raw = (
        graph_weight
        * graph_q
        + tgn_weight
        * tgn_q
    )

    fusion_calibrated = (
        fusion_calibrator
        .predict_proba(
            fusion_raw.reshape(
                -1,
                1,
            )
        )[:, 1]
    )

    graph_raw_metrics = evaluate(
        y,
        graph_raw,
        probability=False,
    )

    graph_cal_metrics = evaluate(
        y,
        graph_calibrated,
        probability=True,
    )

    tgn_metrics = evaluate(
        y,
        tgn_raw,
        probability=False,
    )

    fusion_raw_metrics = evaluate(
        y,
        fusion_raw,
        probability=False,
    )

    fusion_cal_metrics = evaluate(
        y,
        fusion_calibrated,
        probability=True,
    )

    ap_delta = (
        fusion_raw_metrics[
            "average_precision"
        ]
        - graph_raw_metrics[
            "average_precision"
        ]
    )

    recall_delta = (
        fusion_raw_metrics[
            "recall_at_top_1pct"
        ]
        - graph_raw_metrics[
            "recall_at_top_1pct"
        ]
    )

    TEST_PREDICTIONS.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    pl.DataFrame(
        {
            "transaction_id":
                aligned.get_column(
                    "transaction_id"
                ),
            "is_laundering": y,
            "graph_score_raw":
                graph_raw,
            "graph_score_calibrated":
                graph_calibrated,
            "tgn_risk_score":
                tgn_raw,
            "graph_fixed_ecdf":
                graph_q,
            "tgn_fixed_ecdf":
                tgn_q,
            "fusion_score_raw":
                fusion_raw,
            "fusion_score_calibrated":
                fusion_calibrated,
        }
    ).write_parquet(
        TEST_PREDICTIONS,
        compression="zstd",
    )

    report = {
        "status": "PASS",
        "phase": 10,
        "block": "D-one-time-locked-test",
        "evaluation_policy":
            "frozen_after_validation_selection",
        "rows": int(len(y)),
        "positives": int(y.sum()),
        "frozen_graph_weight":
            graph_weight,
        "frozen_tgn_weight":
            tgn_weight,
        "graph_raw":
            graph_raw_metrics,
        "graph_calibrated":
            graph_cal_metrics,
        "tgn":
            tgn_metrics,
        "fusion_raw":
            fusion_raw_metrics,
        "fusion_calibrated":
            fusion_cal_metrics,
        "fusion_ap_delta_vs_graph":
            ap_delta,
        "fusion_recall_at_1pct_delta_vs_graph":
            recall_delta,
        "fusion_beats_graph_on_test_ap":
            ap_delta > 0.0,
        "model_or_weight_tuning_after_test":
            False,
        "calibrator_refit_on_test":
            False,
        "tgn_retrained_for_test":
            False,
        "test_used_for_selection":
            False,
        "test_used_for_calibration_fit":
            False,
        "locked_test_evaluation":
            True,
        "predictions":
            str(TEST_PREDICTIONS),
    }

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Write report last, so the one-time guard trips only
    # after a complete successful evaluation.
    REPORT.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "=== PHASE 10 LOCKED TEST ==="
    )
    print(
        f"ROWS={len(y):,}"
    )
    print(
        f"POSITIVES={int(y.sum()):,}"
    )
    print(
        "GRAPH_AP="
        f"{graph_raw_metrics['average_precision']:.12f}"
    )
    print(
        "GRAPH_RECALL_AT_1PCT="
        f"{graph_raw_metrics['recall_at_top_1pct']:.12f}"
    )
    print(
        "TGN_AP="
        f"{tgn_metrics['average_precision']:.12f}"
    )
    print(
        "TGN_RECALL_AT_1PCT="
        f"{tgn_metrics['recall_at_top_1pct']:.12f}"
    )
    print(
        "FUSION_AP="
        f"{fusion_raw_metrics['average_precision']:.12f}"
    )
    print(
        "FUSION_RECALL_AT_1PCT="
        f"{fusion_raw_metrics['recall_at_top_1pct']:.12f}"
    )
    print(
        f"FUSION_AP_DELTA_VS_GRAPH="
        f"{ap_delta:.12f}"
    )
    print(
        f"FUSION_RECALL_DELTA_VS_GRAPH="
        f"{recall_delta:.12f}"
    )
    print(
        "FUSION_CALIBRATED_BRIER="
        f"{fusion_cal_metrics['brier_score']:.12f}"
    )
    print(
        "FUSION_CALIBRATED_ECE_10="
        f"{fusion_cal_metrics['ece_10_bins']:.12f}"
    )
    print(
        "FUSION_BEATS_GRAPH_ON_TEST_AP="
        + (
            "TRUE"
            if ap_delta > 0.0
            else "FALSE"
        )
    )
    print(
        "MODEL_OR_WEIGHT_TUNING_AFTER_TEST=FALSE"
    )
    print(
        "CALIBRATOR_REFIT_ON_TEST=FALSE"
    )
    print(
        "TGN_RETRAINED_FOR_TEST=FALSE"
    )
    print(
        "TEST_USED_FOR_SELECTION=FALSE"
    )
    print(
        "TEST_USED_FOR_CALIBRATION_FIT=FALSE"
    )
    print(
        f"REPORT={REPORT}"
    )
    print(
        "GRAPHSHIELD_PHASE10_LOCKED_TEST=PASS"
    )


if __name__ == "__main__":
    main()
