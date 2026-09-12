from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import polars as pl
import torch
from sklearn.metrics import average_precision_score, roc_auc_score


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


CHECKPOINT = ROOT / "models" / "v2" / "tgn_phase10c" / "tgn_risk.pt"
SELECTION_TGN = (
    ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "tgn_phase10c"
    / "tgn_validation_predictions.parquet"
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
SELECTION_REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "validation_fusion_v1_report.json"
)

FULL_TGN_OUT = (
    ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "tgn_phase10c"
    / "tgn_validation_full_predictions.parquet"
)
ECDF_OUT = ROOT / "models" / "v2" / "phase10_fusion_ecdf_v1.npz"
HOLDOUT_OUT = (
    ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "phase10"
    / "validation_fusion_holdout_v1.parquet"
)
REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "validation_fusion_holdout_v1_report.json"
)

TRAIN_PREFIX = 750_000
TEST_PLACEHOLDER = 1


def top1(y: np.ndarray, scores: np.ndarray) -> dict:
    n = len(y)
    k = max(1, int(np.ceil(n * 0.01)))
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
        "lift_at_top_1pct": precision / prevalence if prevalence else 0.0,
    }


def metrics(y: np.ndarray, scores: np.ndarray) -> dict:
    out = {
        "rows": int(len(y)),
        "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "average_precision": float(average_precision_score(y, scores)),
    }
    try:
        out["roc_auc"] = float(roc_auc_score(y, scores))
    except ValueError:
        out["roc_auc"] = None
    out.update(top1(y, scores))
    return out


def fixed_ecdf(values: np.ndarray, sorted_reference: np.ndarray) -> np.ndarray:
    # Frozen transformation learned only from the 100k selection slice.
    # Unlike recomputing ranks on a new evaluation set, this can be applied
    # unchanged to later validation/test/live scores.
    return (
        np.searchsorted(
            sorted_reference,
            np.asarray(values, dtype=float),
            side="right",
        )
        / float(len(sorted_reference))
    )


def feature_names(model) -> list[str]:
    names = getattr(model, "feature_name_", None)
    if names is None and hasattr(model, "booster_"):
        names = model.booster_.feature_name()
    if names is None:
        raise RuntimeError("Could not read graph model feature names.")
    return list(names)


def prepare(
    rows: list[dict],
    names: list[str],
    categoricals: list[str],
) -> pd.DataFrame:
    frame = pd.DataFrame(rows).loc[:, names].copy()
    cat_set = set(categoricals)
    for name in names:
        if name in cat_set:
            frame[name] = frame[name].astype("category")
        else:
            frame[name] = pd.to_numeric(
                frame[name],
                errors="raise",
            ).astype("float64")
    return frame


def load_tgn_checkpoint(device):
    checkpoint = torch.load(
        CHECKPOINT,
        map_location=device,
    )
    config = checkpoint["config"]
    return checkpoint, config


def generate_full_validation_predictions() -> pl.DataFrame:
    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    print(f"DEVICE={device}")
    print("TGN_RETRAINING=FALSE")
    print("LOCKED_TEST_EVALUATED=FALSE")
    print(f"TRAIN_HISTORY_PREFIX={TRAIN_PREFIX:,}")
    print("FULL_VALIDATION_SCORING=TRUE")

    checkpoint, config = load_tgn_checkpoint(device)

    print("LOADING_TEMPORAL_BUNDLE=START")
    bundle = load_event_bundle(
        max_train_events=TRAIN_PREFIX,
        max_val_events=None,
        max_test_events=TEST_PLACEHOLDER,
    )
    print("LOADING_TEMPORAL_BUNDLE=PASS")

    system = build_system(
        bundle,
        device,
        memory_dim=int(config["memory_dim"]),
        time_dim=int(config["time_dim"]),
        embedding_dim=int(config["embedding_dim"]),
        neighbor_size=int(config["neighbor_size"]),
    )

    load_parameter_state(
        system.memory,
        checkpoint["memory_parameters"],
    )
    system.gnn.load_state_dict(checkpoint["gnn_state"])
    system.classifier.load_state_dict(checkpoint["classifier_state"])

    reset_system(system)
    system.memory.eval()
    system.gnn.eval()
    system.classifier.eval()

    print("REPLAYING_FROZEN_TRAIN_HISTORY=START")
    replay_split(
        bundle,
        system,
        device,
        "train",
    )
    print("REPLAYING_FROZEN_TRAIN_HISTORY=PASS")

    print("SCORING_FULL_VALIDATION=START")
    y_val, tgn_scores = evaluate_split(
        bundle,
        system,
        device,
        "validation",
    )
    print("SCORING_FULL_VALIDATION=PASS")

    out = pl.DataFrame(
        {
            "transaction_id": bundle.ids["validation"],
            "is_laundering": y_val,
            "tgn_risk_score": tgn_scores,
        }
    )

    FULL_TGN_OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    out.write_parquet(
        FULL_TGN_OUT,
        compression="zstd",
    )
    return out


def main() -> None:
    for path in (
        CHECKPOINT,
        SELECTION_TGN,
        GOLD,
        GRAPH_MODEL,
        GRAPH_CAL,
        SELECTION_REPORT,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    selection_report = json.loads(
        SELECTION_REPORT.read_text(encoding="utf-8")
    )
    selected = selection_report["selected"]
    graph_weight = float(selected["graph_weight"])
    tgn_weight = float(selected["tgn_weight"])

    if abs(graph_weight - 0.99) > 1e-12 or abs(tgn_weight - 0.01) > 1e-12:
        raise RuntimeError(
            "Expected frozen Phase 10D weights 0.99/0.01, got "
            f"{graph_weight}/{tgn_weight}"
        )

    print("=" * 96)
    print("GraphShield AML - Phase 10D - Fusion Confirmation Holdout")
    print("=" * 96)
    print(f"FROZEN_GRAPH_WEIGHT={graph_weight:.2f}")
    print(f"FROZEN_TGN_WEIGHT={tgn_weight:.2f}")
    print("WEIGHTS_TUNED_AGAIN=FALSE")
    print("LOCKED_TEST_READ=FALSE")

    # First 100k validation rows were already used to choose the fusion weight.
    selection_tgn = (
        pl.read_parquet(SELECTION_TGN)
        .select(
            [
                pl.col("transaction_id").cast(pl.String),
                pl.col("is_laundering").cast(pl.Int8),
                pl.col("tgn_risk_score").cast(pl.Float64),
            ]
        )
    )
    selection_ids = selection_tgn.get_column("transaction_id").to_list()

    model = joblib.load(GRAPH_MODEL)
    cal = joblib.load(GRAPH_CAL)
    names = list(cal["feature_names"])
    categoricals = list(cal["categorical_features"])

    if feature_names(model) != names:
        raise RuntimeError("Graph model/calibration schema mismatch.")

    # Fit the deployable score->quantile transforms on selection data only.
    selection_gold = (
        pl.scan_parquet(GOLD)
        .filter(
            (pl.col("split") == "validation")
            & pl.col("transaction_id").cast(pl.String).is_in(selection_ids)
        )
        .select(
            [
                pl.col("transaction_id").cast(pl.String),
                *names,
            ]
        )
        .collect()
    )

    selection_join = selection_tgn.join(
        selection_gold,
        on="transaction_id",
        how="inner",
        validate="1:1",
    )

    if selection_join.height != selection_tgn.height:
        raise RuntimeError("Selection feature alignment failed.")

    selection_X = prepare(
        selection_join.select(names).to_dicts(),
        names,
        categoricals,
    )
    selection_graph_raw = np.asarray(
        model.predict_proba(selection_X)[:, 1],
        dtype=float,
    )
    selection_tgn_raw = selection_join.get_column(
        "tgn_risk_score"
    ).to_numpy()

    graph_ref = np.sort(selection_graph_raw)
    tgn_ref = np.sort(selection_tgn_raw)

    ECDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        ECDF_OUT,
        graph_reference_sorted=graph_ref,
        tgn_reference_sorted=tgn_ref,
        graph_weight=np.asarray([graph_weight]),
        tgn_weight=np.asarray([tgn_weight]),
    )

    # Generate full validation TGN predictions using the already-selected
    # checkpoint. No optimizer/training step occurs here.
    full_tgn = generate_full_validation_predictions().with_columns(
        pl.col("transaction_id").cast(pl.String),
        pl.col("is_laundering").cast(pl.Int8),
        pl.col("tgn_risk_score").cast(pl.Float64),
    )

    if full_tgn.get_column("transaction_id").n_unique() != full_tgn.height:
        raise RuntimeError("Duplicate full-validation TGN transaction IDs.")

    # Confirmation holdout = every validation event not used for weight selection.
    holdout_tgn = full_tgn.filter(
        ~pl.col("transaction_id").is_in(selection_ids)
    )

    if holdout_tgn.height < 1:
        raise RuntimeError("Fusion confirmation holdout is empty.")

    holdout_ids = holdout_tgn.get_column("transaction_id").to_list()

    holdout_gold = (
        pl.scan_parquet(GOLD)
        .filter(
            (pl.col("split") == "validation")
            & pl.col("transaction_id").cast(pl.String).is_in(holdout_ids)
        )
        .select(
            [
                pl.col("transaction_id").cast(pl.String),
                pl.col("is_laundering").cast(pl.Int8).alias("gold_label"),
                *names,
            ]
        )
        .collect()
    )

    aligned = holdout_tgn.join(
        holdout_gold,
        on="transaction_id",
        how="inner",
        validate="1:1",
    )

    if aligned.height != holdout_tgn.height:
        raise RuntimeError("Holdout alignment failed.")

    mismatched_labels = aligned.filter(
        pl.col("is_laundering") != pl.col("gold_label")
    ).height
    if mismatched_labels:
        raise RuntimeError(
            f"Holdout label mismatch: {mismatched_labels}"
        )

    X = prepare(
        aligned.select(names).to_dicts(),
        names,
        categoricals,
    )
    graph_raw = np.asarray(
        model.predict_proba(X)[:, 1],
        dtype=float,
    )
    tgn_raw = aligned.get_column("tgn_risk_score").to_numpy()
    y = aligned.get_column("is_laundering").to_numpy().astype(int)

    graph_q = fixed_ecdf(graph_raw, graph_ref)
    tgn_q = fixed_ecdf(tgn_raw, tgn_ref)
    fused = graph_weight * graph_q + tgn_weight * tgn_q

    graph_m = metrics(y, graph_raw)
    tgn_m = metrics(y, tgn_raw)
    fusion_m = metrics(y, fused)

    ap_delta = (
        fusion_m["average_precision"]
        - graph_m["average_precision"]
    )
    recall_delta = (
        fusion_m["recall_at_top_1pct"]
        - graph_m["recall_at_top_1pct"]
    )

    confirmed = ap_delta > 0.0

    HOLDOUT_OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    pl.DataFrame(
        {
            "transaction_id": aligned.get_column("transaction_id"),
            "is_laundering": y,
            "graph_score_raw": graph_raw,
            "tgn_risk_score": tgn_raw,
            "graph_fixed_ecdf": graph_q,
            "tgn_fixed_ecdf": tgn_q,
            "frozen_fusion_score": fused,
        }
    ).write_parquet(
        HOLDOUT_OUT,
        compression="zstd",
    )

    report = {
        "status": "PASS",
        "phase": 10,
        "block": "D-fusion-confirmation-holdout",
        "selection_rows": int(selection_tgn.height),
        "confirmation_rows": int(len(y)),
        "confirmation_positives": int(y.sum()),
        "frozen_graph_weight": graph_weight,
        "frozen_tgn_weight": tgn_weight,
        "transform": "selection_slice_fixed_ecdf",
        "weights_tuned_on_confirmation": False,
        "graph_only": graph_m,
        "tgn_only": tgn_m,
        "frozen_fusion": fusion_m,
        "fusion_ap_delta_vs_graph": ap_delta,
        "fusion_recall_at_1pct_delta_vs_graph": recall_delta,
        "fusion_confirmed": confirmed,
        "locked_test_read": False,
        "test_used_for_selection": False,
        "tgn_retrained": False,
        "tgn_checkpoint": str(CHECKPOINT),
        "ecdf_artifact": str(ECDF_OUT),
        "full_validation_tgn_predictions": str(FULL_TGN_OUT),
        "holdout_predictions": str(HOLDOUT_OUT),
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print()
    print("=== CONFIRMATION HOLDOUT ===")
    print(f"ROWS={len(y):,}")
    print(f"POSITIVES={int(y.sum()):,}")
    print(
        "GRAPH_AP="
        f"{graph_m['average_precision']:.12f}"
    )
    print(
        "FUSION_AP="
        f"{fusion_m['average_precision']:.12f}"
    )
    print(f"AP_DELTA={ap_delta:.12f}")
    print(
        "GRAPH_RECALL_AT_1PCT="
        f"{graph_m['recall_at_top_1pct']:.12f}"
    )
    print(
        "FUSION_RECALL_AT_1PCT="
        f"{fusion_m['recall_at_top_1pct']:.12f}"
    )
    print(f"RECALL_DELTA={recall_delta:.12f}")
    print(
        "FUSION_CONFIRMED="
        + ("TRUE" if confirmed else "FALSE")
    )
    print("WEIGHTS_TUNED_AGAIN=FALSE")
    print("LOCKED_TEST_READ=FALSE")
    print("TEST_USED_FOR_SELECTION=FALSE")
    print("TGN_RETRAINED=FALSE")
    print(f"REPORT={REPORT}")
    print("GRAPHSHIELD_PHASE10_BLOCK_D_HOLDOUT=PASS")


if __name__ == "__main__":
    main()
