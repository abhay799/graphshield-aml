from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import average_precision_score, roc_auc_score


ROOT = Path(__file__).resolve().parents[2]

TGN_PRED = (
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

REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "validation_fusion_v1_report.json"
)

OUTPUT = (
    ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "phase10"
    / "validation_fusion_v1.parquet"
)

# Pre-declared coarse weights to reduce validation over-search.
# Weight is the contribution from the graph rank; TGN gets (1 - weight).
GRAPH_WEIGHTS = [1.00, 0.99, 0.95, 0.90, 0.80, 0.70, 0.50]


def top_fraction_metrics(y: np.ndarray, scores: np.ndarray, fraction: float = 0.01):
    n = len(y)
    k = max(1, int(np.ceil(n * fraction)))
    order = np.argsort(-scores, kind="mergesort")
    top = order[:k]

    positives = int(y.sum())
    tp = int(y[top].sum())

    precision = tp / k
    recall = tp / positives if positives else 0.0
    prevalence = positives / n if n else 0.0
    lift = precision / prevalence if prevalence > 0 else 0.0

    return {
        "k": k,
        "precision_at_top_1pct": precision,
        "recall_at_top_1pct": recall,
        "lift_at_top_1pct": lift,
    }


def evaluate(y: np.ndarray, scores: np.ndarray) -> dict:
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

    out.update(top_fraction_metrics(y, scores))
    return out


def percentile_rank(values: np.ndarray) -> np.ndarray:
    # Stable average ranks in [0,1]. This makes graph/TGN scales comparable
    # for a ranking-only fusion experiment without pretending both models are
    # equally calibrated probabilities.
    s = pd.Series(np.asarray(values, dtype=float))
    return s.rank(method="average", pct=True).to_numpy(dtype=float)


def model_feature_names(model) -> list[str]:
    names = getattr(model, "feature_name_", None)
    if names is None and hasattr(model, "booster_"):
        names = model.booster_.feature_name()
    if names is None:
        raise RuntimeError("Could not read graph LightGBM feature names.")
    return list(names)


def prepare_frame(
    rows: list[dict],
    feature_names: list[str],
    categorical_features: list[str],
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)

    missing = [name for name in feature_names if name not in frame.columns]
    if missing:
        raise RuntimeError(f"Missing graph model features: {missing}")

    frame = frame.loc[:, feature_names].copy()
    categorical_set = set(categorical_features)

    for name in feature_names:
        if name in categorical_set:
            frame[name] = frame[name].astype("category")
        else:
            frame[name] = pd.to_numeric(
                frame[name],
                errors="raise",
            ).astype("float64")

    return frame


def main() -> None:
    for path in (TGN_PRED, GOLD, GRAPH_MODEL, GRAPH_CAL):
        if not path.exists():
            raise FileNotFoundError(path)

    print("=" * 92)
    print("GraphShield AML - Phase 10D - Validation-Only Graph + TGN Fusion")
    print("=" * 92)
    print("LOCKED_TEST_READ=FALSE")
    print("SELECTION_SPLIT=VALIDATION_ONLY")
    print("FUSION_TYPE=RANK_NORMALIZED_CONVEX")
    print(f"TGN_INPUT={TGN_PRED}")

    tgn = (
        pl.read_parquet(TGN_PRED)
        .select(
            [
                pl.col("transaction_id").cast(pl.String),
                pl.col("is_laundering").cast(pl.Int8),
                pl.col("tgn_risk_score").cast(pl.Float64),
            ]
        )
    )

    if tgn.height == 0:
        raise RuntimeError("TGN validation prediction artifact is empty.")

    if tgn.get_column("transaction_id").n_unique() != tgn.height:
        raise RuntimeError("Duplicate transaction_id values in TGN validation predictions.")

    txids = tgn.get_column("transaction_id").to_list()

    model = joblib.load(GRAPH_MODEL)
    bundle = joblib.load(GRAPH_CAL)

    if not isinstance(bundle, dict):
        raise RuntimeError("Graph calibration artifact must be a dictionary bundle.")

    feature_names = list(bundle["feature_names"])
    categorical_features = list(bundle["categorical_features"])

    if model_feature_names(model) != feature_names:
        raise RuntimeError("Graph model/calibration feature order mismatch.")

    # Gold is filtered strictly to transaction IDs already present in the
    # validation-only TGN artifact. No test rows are selected.
    gold = (
        pl.scan_parquet(GOLD)
        .filter(
            (pl.col("split") == "validation")
            & pl.col("transaction_id").cast(pl.String).is_in(txids)
        )
        .select(
            [
                pl.col("transaction_id").cast(pl.String),
                pl.col("is_laundering").cast(pl.Int8).alias("gold_label"),
                *feature_names,
            ]
        )
        .collect()
    )

    if gold.height != tgn.height:
        raise RuntimeError(
            f"Validation alignment mismatch: TGN={tgn.height:,}, GOLD={gold.height:,}"
        )

    aligned = tgn.join(
        gold,
        on="transaction_id",
        how="inner",
        validate="1:1",
    )

    if aligned.height != tgn.height:
        raise RuntimeError("1:1 validation join failed.")

    label_mismatch = int(
        aligned.filter(pl.col("is_laundering") != pl.col("gold_label")).height
    )
    if label_mismatch:
        raise RuntimeError(
            f"Label mismatch between TGN validation and Gold: {label_mismatch}"
        )

    rows = aligned.select(feature_names).to_dicts()
    X = prepare_frame(rows, feature_names, categorical_features)

    graph_raw = np.asarray(model.predict_proba(X)[:, 1], dtype=float)
    tgn_score = aligned.get_column("tgn_risk_score").to_numpy()
    y = aligned.get_column("is_laundering").to_numpy().astype(int)

    graph_rank = percentile_rank(graph_raw)
    tgn_rank = percentile_rank(tgn_score)

    graph_metrics = evaluate(y, graph_raw)
    tgn_metrics = evaluate(y, tgn_score)

    candidates = []

    for graph_weight in GRAPH_WEIGHTS:
        tgn_weight = 1.0 - graph_weight
        fused = graph_weight * graph_rank + tgn_weight * tgn_rank
        metrics = evaluate(y, fused)

        candidates.append(
            {
                "graph_weight": graph_weight,
                "tgn_weight": tgn_weight,
                "metrics": metrics,
            }
        )

    # Select by AP only. Recall@1% is reported, not used as a secondary
    # hidden selector.
    selected = max(
        candidates,
        key=lambda item: item["metrics"]["average_precision"],
    )

    graph_ap = graph_metrics["average_precision"]
    selected_ap = selected["metrics"]["average_precision"]
    graph_recall = graph_metrics["recall_at_top_1pct"]
    selected_recall = selected["metrics"]["recall_at_top_1pct"]

    ap_delta = selected_ap - graph_ap
    recall_delta = selected_recall - graph_recall

    promoted = (
        selected["graph_weight"] < 1.0
        and ap_delta > 0.0
    )

    # Save scores for auditability.
    chosen_fused = (
        selected["graph_weight"] * graph_rank
        + selected["tgn_weight"] * tgn_rank
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    pl.DataFrame(
        {
            "transaction_id": aligned.get_column("transaction_id"),
            "is_laundering": y,
            "graph_score_raw": graph_raw,
            "tgn_risk_score": tgn_score,
            "graph_rank_score": graph_rank,
            "tgn_rank_score": tgn_rank,
            "selected_fusion_score": chosen_fused,
        }
    ).write_parquet(
        OUTPUT,
        compression="zstd",
    )

    report = {
        "status": "PASS",
        "phase": 10,
        "block": "D-validation-fusion",
        "selection_split": "validation_only",
        "locked_test_read": False,
        "rows": int(len(y)),
        "positives": int(y.sum()),
        "fusion_type": "rank_normalized_convex",
        "predeclared_graph_weights": GRAPH_WEIGHTS,
        "graph_only": graph_metrics,
        "tgn_only": tgn_metrics,
        "candidates": candidates,
        "selected": selected,
        "selected_vs_graph_ap_delta": ap_delta,
        "selected_vs_graph_recall_at_1pct_delta": recall_delta,
        "promote_tgn_into_fusion_candidate": promoted,
        "selection_metric": "average_precision",
        "test_used_for_selection": False,
        "output": str(OUTPUT),
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print("=== EXACT COMMON VALIDATION SUBSET ===")
    print(f"ROWS={len(y):,}")
    print(f"POSITIVES={int(y.sum()):,}")

    print()
    print("=== GRAPH ONLY ===")
    print(f"AP={graph_ap:.12f}")
    print(f"RECALL_AT_1PCT={graph_recall:.12f}")

    print()
    print("=== TGN ONLY ===")
    print(f"AP={tgn_metrics['average_precision']:.12f}")
    print(f"RECALL_AT_1PCT={tgn_metrics['recall_at_top_1pct']:.12f}")

    print()
    print("=== FUSION SWEEP ===")
    for item in candidates:
        print(
            "GRAPH_W={:.2f} TGN_W={:.2f} AP={:.12f} RECALL@1%={:.12f}".format(
                item["graph_weight"],
                item["tgn_weight"],
                item["metrics"]["average_precision"],
                item["metrics"]["recall_at_top_1pct"],
            )
        )

    print()
    print("=== SELECTED ===")
    print(f"GRAPH_WEIGHT={selected['graph_weight']:.2f}")
    print(f"TGN_WEIGHT={selected['tgn_weight']:.2f}")
    print(f"AP={selected_ap:.12f}")
    print(f"AP_DELTA_VS_GRAPH={ap_delta:.12f}")
    print(f"RECALL_AT_1PCT={selected_recall:.12f}")
    print(f"RECALL_DELTA_VS_GRAPH={recall_delta:.12f}")
    print(
        "PROMOTE_TGN_INTO_FUSION_CANDIDATE="
        + ("TRUE" if promoted else "FALSE")
    )
    print("LOCKED_TEST_READ=FALSE")
    print("TEST_USED_FOR_SELECTION=FALSE")
    print(f"REPORT={REPORT}")
    print(f"OUTPUT={OUTPUT}")
    print("GRAPHSHIELD_PHASE10_BLOCK_D_VALIDATION_FUSION=PASS")


if __name__ == "__main__":
    main()
