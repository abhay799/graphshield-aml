from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import polars as pl
import yaml
from confluent_kafka import Producer


ROOT = Path(__file__).resolve().parents[2]
STREAMING_DIR = ROOT / "src" / "streaming"

if str(STREAMING_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMING_DIR))

from phase10_b3_online_feature_parity import Engine


SILVER = ROOT / "data" / "processed" / "silver" / "transactions.parquet"
GOLD = ROOT / "data" / "processed" / "gold" / "model_features_v2_graph_split.parquet"
MODEL_PATH = ROOT / "models" / "lightgbm_graph_v1.joblib"
CAL_PATH = ROOT / "models" / "probability_calibrator_graph_v1.joblib"
CONFIG_PATH = ROOT / "configs" / "v2" / "streaming" / "replay.yaml"
REPORT = ROOT / "reports" / "v2" / "phase10" / "stateful_live_scoring_v1_report.json"

MODEL_NAME = "lightgbm_graph"
MODEL_VERSION = "lightgbm_graph_v1"
SCORING_VERSION = "stateful_online_scoring_v1"


def load_first_two_timestamps(max_rows: int = 25000):
    cols = [
        "transaction_id",
        "source_row_number",
        "event_ts",
        "from_bank",
        "from_account",
        "to_bank",
        "to_account",
        "amount_paid",
        "amount_received",
        "payment_currency",
        "receiving_currency",
        "payment_format",
    ]

    frame = (
        pl.scan_parquet(SILVER)
        .select(cols)
        .sort(["event_ts", "source_row_number", "transaction_id"])
        .head(max_rows)
        .collect()
    )

    timestamps = (
        frame.select("event_ts")
        .unique()
        .sort("event_ts")
        .head(2)["event_ts"]
        .to_list()
    )

    if len(timestamps) < 2:
        raise RuntimeError("Could not find two chronological timestamps.")

    first_ts, second_ts = timestamps

    first_group = (
        frame.filter(pl.col("event_ts") == first_ts)
        .sort(["source_row_number", "transaction_id"])
        .to_dicts()
    )

    second_group = (
        frame.filter(pl.col("event_ts") == second_ts)
        .sort(["source_row_number", "transaction_id"])
        .to_dicts()
    )

    return first_ts, second_ts, first_group, second_group


def model_feature_names(model) -> list[str]:
    names = getattr(model, "feature_name_", None)

    if names is None and hasattr(model, "booster_"):
        names = model.booster_.feature_name()

    if names is None:
        raise RuntimeError("Could not read LightGBM feature names.")

    return list(names)


def prepare_pandas(
    rows: list[dict],
    feature_names: list[str],
    categorical_features: list[str],
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)

    missing = [
        name
        for name in feature_names
        if name not in frame.columns
    ]

    if missing:
        raise RuntimeError(
            f"Scoring rows are missing model features: {missing}"
        )

    frame = frame.loc[:, feature_names].copy()

    categorical_set = set(categorical_features)

    for name in feature_names:
        if name in categorical_set:
            # LightGBM restores the training category vocabulary from the
            # fitted booster. Keep categorical columns as pandas category.
            frame[name] = frame[name].astype("category")
        else:
            # A small live batch can contain a numeric feature that is null
            # for every row (for example no previous pair/inbound event).
            # Pandas then infers dtype=object, which LightGBM rejects.
            # Force every non-categorical model feature to a numeric dtype;
            # None becomes NaN, which is LightGBM's normal missing value.
            frame[name] = pd.to_numeric(
                frame[name],
                errors="raise",
            ).astype("float64")

    bad = [
        f"{name}:{frame[name].dtype}"
        for name in feature_names
        if (
            name not in categorical_set
            and not pd.api.types.is_numeric_dtype(frame[name].dtype)
        )
    ]

    if bad:
        raise RuntimeError(
            "Non-categorical model features still have non-numeric dtypes: "
            + ", ".join(bad)
        )

    return frame


def calibrate(calibrator, raw_scores: np.ndarray) -> np.ndarray:
    raw_scores = np.asarray(raw_scores, dtype=float).reshape(-1, 1)

    if hasattr(calibrator, "predict_proba"):
        values = calibrator.predict_proba(raw_scores)[:, 1]
    elif hasattr(calibrator, "predict"):
        values = calibrator.predict(raw_scores)
    else:
        raise RuntimeError(
            "Calibration artifact has neither predict_proba nor predict."
        )

    return np.asarray(values, dtype=float)


def load_gold_feature_rows(
    transaction_ids: list[str],
    feature_names: list[str],
) -> list[dict]:
    frame = (
        pl.scan_parquet(GOLD)
        .filter(pl.col("transaction_id").is_in(transaction_ids))
        .select(["transaction_id", *feature_names])
        .collect()
    )

    if frame.height != len(set(transaction_ids)):
        raise RuntimeError(
            "Gold feature lookup did not return exactly one row per transaction."
        )

    mapping = {
        str(row["transaction_id"]): row
        for row in frame.to_dicts()
    }

    return [
        mapping[str(txid)]
        for txid in transaction_ids
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=25)
    parser.add_argument(
        "--redis-url",
        default="redis://127.0.0.1:6379/0",
    )
    parser.add_argument(
        "--namespace",
        default="gs:p10:live-score-smoke:v1",
    )
    parser.add_argument(
        "--output-topic",
        default="graphshield.scored-transactions.smoke.v1",
    )
    parser.add_argument("--max-source-rows", type=int, default=25000)
    parser.add_argument("--score-atol", type=float, default=1e-12)
    args = parser.parse_args()

    if args.rows < 1 or args.rows > 1000:
        raise ValueError("--rows must be between 1 and 1000.")

    for path in (
        SILVER,
        GOLD,
        MODEL_PATH,
        CAL_PATH,
        CONFIG_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    model = joblib.load(MODEL_PATH)
    bundle = joblib.load(CAL_PATH)

    if not isinstance(bundle, dict):
        raise RuntimeError(
            "Graph calibration artifact must be a dictionary bundle."
        )

    feature_names = list(bundle["feature_names"])
    categorical_features = list(bundle["categorical_features"])
    calibrator = bundle["calibrator"]
    calibration_version = str(
        bundle.get("calibration_version", "platt_graph_v1")
    )

    model_names = model_feature_names(model)

    if model_names != feature_names:
        raise RuntimeError(
            "Model/calibration feature order mismatch.\n"
            f"MODEL={model_names}\n"
            f"CALIBRATION={feature_names}"
        )

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    bootstrap = str(config["bootstrap_servers"])

    print("=" * 92)
    print(
        "GraphShield AML - Phase 10 "
        "- Stateful Live Scoring Smoke v1"
    )
    print("=" * 92)
    print(f"MODEL_FEATURES={len(feature_names)}")
    print(f"MODEL_VERSION={MODEL_VERSION}")
    print(f"CALIBRATION_VERSION={calibration_version}")
    print(f"OUTPUT_TOPIC={args.output_topic}")
    print("LABEL_FIELD_SELECTED=FALSE")
    print("DECISION_SUPPORT_ONLY=TRUE")

    (
        first_ts,
        second_ts,
        first_group,
        second_group,
    ) = load_first_two_timestamps(args.max_source_rows)

    sample = second_group[: args.rows]

    if len(sample) != args.rows:
        raise RuntimeError(
            f"Requested {args.rows} rows but only found {len(sample)}."
        )

    print(f"FIRST_TIMESTAMP={first_ts}")
    print(f"FIRST_TIMESTAMP_ROWS={len(first_group):,}")
    print(f"SECOND_TIMESTAMP={second_ts}")
    print(f"SCORING_ROWS={len(sample):,}")

    engine = Engine(
        args.redis_url,
        args.namespace,
    )

    deleted = engine.clear()
    print(f"SCORING_NAMESPACE_RESET_KEYS={deleted}")

    # Seed the entire first timestamp. This creates genuine prior state for
    # second-timestamp scoring without calculating 70 cold-start features.
    print("SEEDING_PRIOR_STATE=START")

    original_hget = engine.r.hget

    def seed_hget(key, field):
        if field == "first_ts":
            return None
        return original_hget(key, field)

    engine.r.hget = seed_hget

    try:
        engine.commit_group(first_group)
    finally:
        engine.r.hget = original_hget

    print("SEEDING_PRIOR_STATE=PASS")

    # Online Redis-derived features.
    online = engine.feature_group(sample)

    online_feature_rows = [
        result["features"]
        for result in online
    ]

    online_X = prepare_pandas(
        online_feature_rows,
        feature_names,
        categorical_features,
    )

    object_numeric = [
        name
        for name in feature_names
        if (
            name not in set(categorical_features)
            and online_X[name].dtype == "object"
        )
    ]

    if object_numeric:
        raise RuntimeError(
            "Numeric dtype contract failed before LightGBM scoring: "
            f"{object_numeric}"
        )

    print("PANDAS_NUMERIC_DTYPE_CONTRACT=PASS")

    online_raw = np.asarray(
        model.predict_proba(online_X)[:, 1],
        dtype=float,
    )

    online_cal = calibrate(
        calibrator,
        online_raw,
    )

    # Independent score-parity oracle: score the certified Gold feature rows
    # for these exact transactions with the same frozen model/calibrator.
    txids = [
        str(result["transaction_id"])
        for result in online
    ]

    gold_rows = load_gold_feature_rows(
        txids,
        feature_names,
    )

    gold_X = prepare_pandas(
        gold_rows,
        feature_names,
        categorical_features,
    )

    gold_raw = np.asarray(
        model.predict_proba(gold_X)[:, 1],
        dtype=float,
    )

    gold_cal = calibrate(
        calibrator,
        gold_raw,
    )

    raw_max_diff = float(
        np.max(np.abs(online_raw - gold_raw))
    )

    cal_max_diff = float(
        np.max(np.abs(online_cal - gold_cal))
    )

    if raw_max_diff > args.score_atol:
        raise RuntimeError(
            "Online raw-score parity failed: "
            f"max_abs_diff={raw_max_diff}"
        )

    if cal_max_diff > args.score_atol:
        raise RuntimeError(
            "Online calibrated-score parity failed: "
            f"max_abs_diff={cal_max_diff}"
        )

    if np.any((online_raw < 0.0) | (online_raw > 1.0)):
        raise RuntimeError("Raw score outside [0,1].")

    if np.any((online_cal < 0.0) | (online_cal > 1.0)):
        raise RuntimeError("Calibrated score outside [0,1].")

    producer = Producer(
        {
            "bootstrap.servers": bootstrap,
            "enable.idempotence": True,
            "acks": "all",
            "compression.type": "zstd",
            "client.id": "graphshield-stateful-live-scorer-v1",
        }
    )

    produced = 0
    outputs = []

    for index, result in enumerate(online):
        payload = {
            "transaction_id": result["transaction_id"],
            "event_ts": str(result["event_ts"]),
            "risk_score_raw": float(online_raw[index]),
            "risk_score_calibrated": float(online_cal[index]),
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "calibration_version": calibration_version,
            "scoring_version": SCORING_VERSION,
            "feature_source": "redis_strict_pit_state_v1",
            "label_exposure": False,
            "decision_support_only": True,
            "scored_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        if "is_laundering" in payload:
            raise RuntimeError("Output label leakage detected.")

        producer.produce(
            args.output_topic,
            key=str(result["transaction_id"]),
            value=json.dumps(
                payload,
                separators=(",", ":"),
            ).encode("utf-8"),
        )

        outputs.append(payload)
        produced += 1

    remaining = producer.flush(30)

    if remaining != 0:
        raise RuntimeError(
            f"Kafka producer failed to flush {remaining} message(s)."
        )

    # Apply second-timestamp state only AFTER all rows have been featured
    # and published. Same-timestamp rows therefore never see each other.
    engine.commit_group(sample)

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "status": "PASS",
        "phase": 10,
        "block": "B4-stateful-live-scoring",
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "calibration_version": calibration_version,
        "scoring_version": SCORING_VERSION,
        "feature_source": "redis_strict_pit_state_v1",
        "first_timestamp_rows_seeded": len(first_group),
        "second_timestamp_rows_scored": len(sample),
        "output_topic": args.output_topic,
        "output_messages_produced": produced,
        "raw_score_max_abs_diff_vs_certified_gold": raw_max_diff,
        "calibrated_score_max_abs_diff_vs_certified_gold": cal_max_diff,
        "score_tolerance": args.score_atol,
        "label_exposure": False,
        "zero_fill_missing_features": False,
        "current_timestamp_state_visible": False,
        "decision_support_only": True,
        "delivery_semantics": (
            "Kafka output idempotent producer; "
            "this smoke does not claim end-to-end exactly-once"
        ),
    }

    REPORT.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(f"STATEFUL_EVENTS_SCORED={len(sample):,}")
    print(f"KAFKA_OUTPUT_MESSAGES={produced:,}")
    print(f"RAW_SCORE_MAX_ABS_DIFF={raw_max_diff:.16g}")
    print(
        "CALIBRATED_SCORE_MAX_ABS_DIFF="
        f"{cal_max_diff:.16g}"
    )
    print("LABEL_LEAKAGE=NONE")
    print("ZERO_FILL_MISSING_FEATURES=FALSE")
    print("CURRENT_TIMESTAMP_STATE_VISIBLE=FALSE")
    print("DECISION_SUPPORT_ONLY=TRUE")
    print("END_TO_END_EXACTLY_ONCE_CLAIMED=FALSE")
    print(f"REPORT={REPORT}")
    print("GRAPHSHIELD_PHASE10_BLOCK_B4=PASS")


if __name__ == "__main__":
    main()
