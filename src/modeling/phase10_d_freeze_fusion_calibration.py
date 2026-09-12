from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import polars as pl
import pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss


ROOT = Path(__file__).resolve().parents[2]

GOLD = (
    ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

TGN_FULL = (
    ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "tgn_phase10c"
    / "tgn_validation_full_predictions.parquet"
)

GRAPH_MODEL = ROOT / "models" / "lightgbm_graph_v1.joblib"
GRAPH_CAL = ROOT / "models" / "probability_calibrator_graph_v1.joblib"

FUSION_SELECTION_REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "validation_fusion_v1_report.json"
)

FUSION_HOLDOUT_REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "validation_fusion_holdout_v1_report.json"
)

ECDF_PATH = ROOT / "models" / "v2" / "phase10_fusion_ecdf_v1.npz"

VALIDATION_SLICE = (
    ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "phase10"
    / "graph_validation_feature_slice_v1.parquet"
)

VALIDATION_SCORES = (
    ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "phase10"
    / "fusion_validation_scores_v1.parquet"
)

CALIBRATOR_OUT = (
    ROOT
    / "models"
    / "v2"
    / "phase10_fusion_calibrator_v1.joblib"
)

REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "fusion_calibration_v1_report.json"
)

BATCH_SIZE = 50_000


def fixed_ecdf(values: np.ndarray, sorted_reference: np.ndarray) -> np.ndarray:
    return (
        np.searchsorted(
            sorted_reference,
            np.asarray(values, dtype=float),
            side="right",
        )
        / float(len(sorted_reference))
    )


def ece_10(y: np.ndarray, p: np.ndarray) -> float:
    edges = np.linspace(0.0, 1.0, 11)
    total = len(y)
    ece = 0.0

    for i in range(10):
        lo, hi = edges[i], edges[i + 1]
        if i == 9:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)

        n = int(mask.sum())
        if n == 0:
            continue

        conf = float(p[mask].mean())
        acc = float(y[mask].mean())
        ece += (n / total) * abs(acc - conf)

    return float(ece)


def model_feature_names(model) -> list[str]:
    names = getattr(model, "feature_name_", None)
    if names is None and hasattr(model, "booster_"):
        names = model.booster_.feature_name()
    if names is None:
        raise RuntimeError("Could not read LightGBM feature names.")
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
            out[name] = out[name].astype("category")
        else:
            out[name] = pd.to_numeric(
                out[name],
                errors="raise",
            ).astype("float64")

    return out


def score_validation_graph(
    model,
    feature_names: list[str],
    categorical_features: list[str],
) -> pl.DataFrame:
    VALIDATION_SLICE.parent.mkdir(parents=True, exist_ok=True)

    print("BUILD_VALIDATION_ONLY_FEATURE_SLICE=START")

    (
        pl.scan_parquet(GOLD)
        .filter(pl.col("split") == "validation")
        .select(
            [
                pl.col("transaction_id").cast(pl.String),
                pl.col("is_laundering").cast(pl.Int8),
                *feature_names,
            ]
        )
        .sink_parquet(
            VALIDATION_SLICE,
            compression="zstd",
        )
    )

    print("BUILD_VALIDATION_ONLY_FEATURE_SLICE=PASS")

    parquet = pq.ParquetFile(VALIDATION_SLICE)

    txids: list[str] = []
    labels: list[int] = []
    scores: list[float] = []
    done = 0

    print("GRAPH_VALIDATION_SCORING=START")

    for batch in parquet.iter_batches(batch_size=BATCH_SIZE):
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

        txids.extend(df["transaction_id"].astype(str).tolist())
        labels.extend(df["is_laundering"].astype(int).tolist())
        scores.extend(pred.tolist())

        done += len(df)
        if done % 100_000 < BATCH_SIZE:
            print(f"GRAPH_VALIDATION_ROWS_SCORED={done:,}")

    print("GRAPH_VALIDATION_SCORING=PASS")

    return pl.DataFrame(
        {
            "transaction_id": txids,
            "is_laundering": labels,
            "graph_score_raw": scores,
        }
    )


def main() -> None:
    required = [
        GOLD,
        TGN_FULL,
        GRAPH_MODEL,
        GRAPH_CAL,
        FUSION_SELECTION_REPORT,
        FUSION_HOLDOUT_REPORT,
        ECDF_PATH,
    ]

    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

    selection = json.loads(
        FUSION_SELECTION_REPORT.read_text(encoding="utf-8")
    )
    holdout = json.loads(
        FUSION_HOLDOUT_REPORT.read_text(encoding="utf-8")
    )

    if holdout.get("fusion_confirmed") is not True:
        raise RuntimeError(
            "Fusion confirmation holdout did not confirm the candidate."
        )

    graph_weight = float(selection["selected"]["graph_weight"])
    tgn_weight = float(selection["selected"]["tgn_weight"])

    if abs(graph_weight - 0.99) > 1e-12 or abs(tgn_weight - 0.01) > 1e-12:
        raise RuntimeError(
            f"Unexpected frozen weights: {graph_weight}/{tgn_weight}"
        )

    model = joblib.load(GRAPH_MODEL)
    graph_cal_bundle = joblib.load(GRAPH_CAL)

    feature_names = list(graph_cal_bundle["feature_names"])
    categorical_features = list(
        graph_cal_bundle["categorical_features"]
    )

    if model_feature_names(model) != feature_names:
        raise RuntimeError("Graph model feature schema mismatch.")

    ecdf = np.load(ECDF_PATH)
    graph_ref = np.asarray(
        ecdf["graph_reference_sorted"],
        dtype=float,
    )
    tgn_ref = np.asarray(
        ecdf["tgn_reference_sorted"],
        dtype=float,
    )

    print("=" * 94)
    print("GraphShield AML - Phase 10D - Freeze Fusion + Calibration")
    print("=" * 94)
    print(f"FROZEN_GRAPH_WEIGHT={graph_weight:.2f}")
    print(f"FROZEN_TGN_WEIGHT={tgn_weight:.2f}")
    print("FUSION_WEIGHTS_TUNED_AGAIN=FALSE")
    print("TEST_ROWS_SELECTED=FALSE")
    print("TEST_USED_FOR_SELECTION=FALSE")

    graph = score_validation_graph(
        model,
        feature_names,
        categorical_features,
    )

    tgn = (
        pl.read_parquet(TGN_FULL)
        .with_row_index("validation_order")
        .select(
            [
                "validation_order",
                pl.col("transaction_id").cast(pl.String),
                pl.col("is_laundering").cast(pl.Int8).alias("tgn_label"),
                pl.col("tgn_risk_score").cast(pl.Float64),
            ]
        )
    )

    if tgn.height == 0:
        raise RuntimeError("Full validation TGN predictions are empty.")

    aligned = (
        tgn.join(
            graph,
            on="transaction_id",
            how="inner",
            validate="1:1",
        )
        .sort("validation_order")
    )

    if aligned.height != tgn.height or aligned.height != graph.height:
        raise RuntimeError(
            f"Validation alignment mismatch: "
            f"TGN={tgn.height:,}, GRAPH={graph.height:,}, JOIN={aligned.height:,}"
        )

    mismatches = aligned.filter(
        pl.col("tgn_label") != pl.col("is_laundering")
    ).height

    if mismatches:
        raise RuntimeError(f"Validation label mismatches: {mismatches}")

    y = aligned.get_column("is_laundering").to_numpy().astype(int)
    graph_raw = aligned.get_column("graph_score_raw").to_numpy()
    tgn_raw = aligned.get_column("tgn_risk_score").to_numpy()

    graph_q = fixed_ecdf(graph_raw, graph_ref)
    tgn_q = fixed_ecdf(tgn_raw, tgn_ref)

    fusion_raw = (
        graph_weight * graph_q
        + tgn_weight * tgn_q
    )

    # Chronological diagnostic split:
    # fit Platt on first half, evaluate on later half.
    n = len(y)
    cut = n // 2

    X_fit = fusion_raw[:cut].reshape(-1, 1)
    y_fit = y[:cut]
    X_eval = fusion_raw[cut:].reshape(-1, 1)
    y_eval = y[cut:]

    diagnostic_calibrator = LogisticRegression(
        C=1e6,
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    diagnostic_calibrator.fit(X_fit, y_fit)

    eval_prob = diagnostic_calibrator.predict_proba(X_eval)[:, 1]

    diagnostic = {
        "fit_rows": int(len(y_fit)),
        "fit_positives": int(y_fit.sum()),
        "eval_rows": int(len(y_eval)),
        "eval_positives": int(y_eval.sum()),
        "eval_average_precision": float(
            average_precision_score(y_eval, eval_prob)
        ),
        "eval_brier_score": float(
            brier_score_loss(y_eval, eval_prob)
        ),
        "eval_ece_10_bins": ece_10(y_eval, eval_prob),
    }

    # After the calibration method is fixed, refit Platt on all validation
    # rows for the final artifact. Test remains unused.
    final_calibrator = LogisticRegression(
        C=1e6,
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    final_calibrator.fit(
        fusion_raw.reshape(-1, 1),
        y,
    )

    final_validation_prob = final_calibrator.predict_proba(
        fusion_raw.reshape(-1, 1)
    )[:, 1]

    CALIBRATOR_OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        {
            "version": "phase10_graph_tgn_fusion_platt_v1",
            "graph_weight": graph_weight,
            "tgn_weight": tgn_weight,
            "fusion_type": "fixed_ecdf_rank_fusion",
            "graph_reference_sorted": graph_ref,
            "tgn_reference_sorted": tgn_ref,
            "calibrator": final_calibrator,
            "graph_model_path": str(GRAPH_MODEL),
            "tgn_checkpoint_path": str(
                ROOT
                / "models"
                / "v2"
                / "tgn_phase10c"
                / "tgn_risk.pt"
            ),
            "calibration_fit_split": "full_validation_after_fusion_confirmation",
            "test_used_for_fit": False,
        },
        CALIBRATOR_OUT,
    )

    VALIDATION_SCORES.parent.mkdir(
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
            "fusion_score_raw": fusion_raw,
            "fusion_score_calibrated": final_validation_prob,
        }
    ).write_parquet(
        VALIDATION_SCORES,
        compression="zstd",
    )

    report = {
        "status": "PASS",
        "phase": 10,
        "block": "D-freeze-fusion-calibration",
        "validation_rows": int(n),
        "validation_positives": int(y.sum()),
        "frozen_graph_weight": graph_weight,
        "frozen_tgn_weight": tgn_weight,
        "fusion_type": "fixed_ecdf_rank_fusion",
        "fusion_weights_tuned_again": False,
        "calibration_method": "platt_logistic_regression",
        "chronological_calibration_diagnostic": diagnostic,
        "final_calibrator_fit_rows": int(n),
        "final_calibrator_fit_positives": int(y.sum()),
        "test_rows_selected": False,
        "test_used_for_selection": False,
        "test_used_for_calibration_fit": False,
        "calibrator_artifact": str(CALIBRATOR_OUT),
        "validation_scores": str(VALIDATION_SCORES),
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print()
    print("=== CALIBRATION DIAGNOSTIC ===")
    print(f"FIT_ROWS={diagnostic['fit_rows']:,}")
    print(f"FIT_POSITIVES={diagnostic['fit_positives']:,}")
    print(f"EVAL_ROWS={diagnostic['eval_rows']:,}")
    print(f"EVAL_POSITIVES={diagnostic['eval_positives']:,}")
    print(
        "EVAL_BRIER="
        f"{diagnostic['eval_brier_score']:.12f}"
    )
    print(
        "EVAL_ECE_10="
        f"{diagnostic['eval_ece_10_bins']:.12f}"
    )
    print()
    print("FINAL_CALIBRATOR_FIT=FULL_VALIDATION")
    print("FUSION_WEIGHTS_TUNED_AGAIN=FALSE")
    print("TEST_ROWS_SELECTED=FALSE")
    print("TEST_USED_FOR_SELECTION=FALSE")
    print("TEST_USED_FOR_CALIBRATION_FIT=FALSE")
    print(f"CALIBRATOR={CALIBRATOR_OUT}")
    print(f"REPORT={REPORT}")
    print("GRAPHSHIELD_PHASE10_BLOCK_D_CALIBRATION=PASS")


if __name__ == "__main__":
    main()
