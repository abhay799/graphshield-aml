from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from itertools import groupby
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import joblib
import numpy as np
import pandas as pd
import polars as pl

from services.live_scoring_feature_wrapper import FrozenModelFeatureWrapper

SILVER_PATH = ROOT / "data" / "processed" / "silver" / "transactions.parquet"
GOLD_PATH = ROOT / "data" / "processed" / "gold" / "model_features_v2_graph_split.parquet"
MODEL_PATH = ROOT / "models" / "lightgbm_graph_v1.joblib"
CALIBRATOR_PATH = ROOT / "models" / "probability_calibrator_graph_v1.joblib"
CONTRACT_PATH = ROOT / "reports" / "v2" / "phase10" / "live_feature_contract_v1.json"
DEFAULT_OUTPUT = ROOT / "reports" / "v2" / "phase10" / "historical_pit_replay_v1.json"

DEFAULT_TARGET_IDS = ["IBM_LI_SMALL_4884658"]
DEFAULT_NAMESPACE = "gs:l4c:historical-replay:v1"
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"

RAW_COLUMNS = [
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

CERTIFIED_REFERENCES = {
    "IBM_LI_SMALL_4884658": {
        "raw_model_score": 0.9999999999996636,
        "calibrated_score": 0.02738545245606547,
    }
}


def load_targets(target_ids: Iterable[str]) -> list[dict[str, Any]]:
    ids = [str(value) for value in target_ids]
    if not ids:
        raise ValueError("at least one target transaction ID is required")

    frame = (
        pl.scan_parquet(SILVER_PATH)
        .filter(pl.col("transaction_id").is_in(ids))
        .select(RAW_COLUMNS)
        .collect(engine="streaming")
    )
    found = set(frame["transaction_id"].to_list())
    missing = [target_id for target_id in ids if target_id not in found]
    if missing:
        raise ValueError(f"target transaction IDs not found: {missing}")

    return frame.sort(
        ["event_ts", "source_row_number", "transaction_id"]
    ).to_dicts()


def select_replay_history(target: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the exact L2 case-specific PIT replay scope for one target."""
    target_ts = target["event_ts"]
    from_bank = str(target["from_bank"])
    sender_key = f"{target['from_bank']}::{target['from_account']}"
    receiver_key = f"{target['to_bank']}::{target['to_account']}"

    return (
        pl.scan_parquet(SILVER_PATH)
        .select(RAW_COLUMNS)
        .with_columns(
            [
                pl.concat_str(
                    [
                        pl.col("from_bank").cast(pl.String),
                        pl.col("from_account").cast(pl.String),
                    ],
                    separator="::",
                ).alias("_sender_key"),
                pl.concat_str(
                    [
                        pl.col("to_bank").cast(pl.String),
                        pl.col("to_account").cast(pl.String),
                    ],
                    separator="::",
                ).alias("_receiver_key"),
            ]
        )
        .filter(
            (pl.col("event_ts") < pl.lit(target_ts))
            & (
                (pl.col("from_bank").cast(pl.String) == from_bank)
                | (pl.col("_sender_key") == sender_key)
                | (pl.col("_receiver_key") == sender_key)
                | (pl.col("_sender_key") == receiver_key)
                | (pl.col("_receiver_key") == receiver_key)
            )
        )
        .drop(["_sender_key", "_receiver_key"])
        .sort(["event_ts", "source_row_number", "transaction_id"])
        .collect(engine="streaming")
        .to_dicts()
    )


def _build_union_replay_stream(
    targets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Union target-specific L2 scopes and targets, de-duplicated by tx ID."""
    rows_by_id: dict[str, dict[str, Any]] = {}
    history_counts: dict[str, int] = {}

    for target in targets:
        history = select_replay_history(target)
        target_id = str(target["transaction_id"])
        history_counts[target_id] = len(history)
        for row in history:
            rows_by_id.setdefault(str(row["transaction_id"]), row)
        rows_by_id.setdefault(target_id, target)

    rows = sorted(
        rows_by_id.values(),
        key=lambda row: (
            row["event_ts"],
            int(row.get("source_row_number", 0)),
            str(row["transaction_id"]),
        ),
    )
    return rows, history_counts


def _load_model_bundle() -> tuple[Any, dict[str, Any], list[str], list[str]]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("status") != "PASS":
        raise RuntimeError("live feature contract is not certified PASS")
    if contract.get("label_leakage_allowed") is not False:
        raise RuntimeError("live feature contract permits label leakage")

    feature_names = list(contract["model_features"])
    if len(feature_names) != 70:
        raise RuntimeError("historical replay requires exactly 70 model features")

    model = joblib.load(MODEL_PATH)
    bundle = joblib.load(CALIBRATOR_PATH)
    if list(getattr(model, "feature_name_", [])) != feature_names:
        raise RuntimeError("frozen model feature order does not match contract")
    if list(bundle.get("feature_names", [])) != feature_names:
        raise RuntimeError("calibrator feature order does not match contract")

    categorical = list(bundle.get("categorical_features", []))
    return model, bundle, feature_names, categorical


def _model_frame(
    features: dict[str, Any],
    feature_names: list[str],
    categorical_features: list[str],
) -> pd.DataFrame:
    frame = pd.DataFrame(
        [{name: features.get(name) for name in feature_names}],
        columns=feature_names,
    )
    for name in feature_names:
        if name in categorical_features:
            frame[name] = (
                frame[name]
                .fillna("__MISSING__")
                .astype("string")
                .astype("category")
            )
        else:
            frame[name] = pd.to_numeric(
                frame[name], errors="coerce"
            ).astype("float32")
    return frame


def _logit(probability: float) -> float:
    value = float(np.clip(probability, 1e-6, 1 - 1e-6))
    return math.log(value / (1.0 - value))


def _score_feature_vector(
    features: dict[str, Any],
    model: Any,
    bundle: dict[str, Any],
    feature_names: list[str],
    categorical_features: list[str],
) -> tuple[float, float]:
    frame = _model_frame(
        features,
        feature_names,
        categorical_features,
    )
    raw_score = float(model.predict_proba(frame)[0, 1])
    calibrated_score = float(
        bundle["calibrator"].predict_proba(
            np.asarray([[_logit(raw_score)]], dtype=float)
        )[0, 1]
    )
    return raw_score, calibrated_score


def _certified_gold_features(
    transaction_id: str,
    feature_names: list[str],
) -> dict[str, Any]:
    rows = (
        pl.scan_parquet(GOLD_PATH)
        .filter(pl.col("transaction_id") == transaction_id)
        .select(["transaction_id", *feature_names])
        .collect(engine="streaming")
        .to_dicts()
    )
    if len(rows) != 1:
        raise RuntimeError(
            f"certified gold lookup expected one row for {transaction_id}, "
            f"found {len(rows)}"
        )
    return {name: rows[0][name] for name in feature_names}


def _same_value(left: Any, right: Any) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    if isinstance(left, str) or isinstance(right, str):
        return str(left) == str(right)
    try:
        left_float = float(left)
        right_float = float(right)
    except (TypeError, ValueError):
        return left == right
    if math.isnan(left_float) and math.isnan(right_float):
        return True
    return math.isclose(
        left_float,
        right_float,
        rel_tol=1e-9,
        abs_tol=1e-9,
    )


def _replay_prior_history(
    wrapper: FrozenModelFeatureWrapper,
    history: list[dict[str, Any]],
) -> int:
    timestamp_groups = 0
    for _, iterator in groupby(
        history,
        key=lambda row: row["event_ts"],
    ):
        group = list(iterator)
        # Certification path deliberately bypasses Mode A and calls the
        # unchanged certified Engine directly.
        wrapper.engine.commit_group(group)
        timestamp_groups += 1
    return timestamp_groups


def run_historical_replay(
    *,
    target_ids: list[str] | None = None,
    redis_url: str = DEFAULT_REDIS_URL,
    namespace: str = DEFAULT_NAMESPACE,
    output_path: str | Path | None = DEFAULT_OUTPUT,
    clear_namespace: bool = True,
    cleanup_after: bool = True,
) -> dict[str, Any]:
    target_ids = list(target_ids or DEFAULT_TARGET_IDS)
    targets = load_targets(target_ids)

    targets_by_ts: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for target in targets:
        targets_by_ts[target["event_ts"]].append(target)

    stream, history_counts = _build_union_replay_stream(targets)
    model, bundle, feature_names, categorical_features = _load_model_bundle()
    wrapper = FrozenModelFeatureWrapper(redis_url, namespace)

    if clear_namespace:
        cleared_before = wrapper.clear()
    else:
        existing = next(
            wrapper.engine.r.scan_iter(
                match=f"{namespace.rstrip(':')}:*",
                count=1,
            ),
            None,
        )
        if existing is not None:
            raise RuntimeError(
                "historical PIT namespace must be empty when clear_namespace=False"
            )
        cleared_before = 0

    results: list[dict[str, Any]] = []
    committed_rows = 0
    committed_groups = 0
    cleanup_deleted_keys = 0
    started = time.monotonic()

    try:
        for event_ts, iterator in groupby(
            stream,
            key=lambda row: row["event_ts"],
        ):
            group = list(iterator)
            targets_here = targets_by_ts.get(event_ts, [])

            if targets_here:
                # Strict PIT: feature the complete timestamp group before any
                # event at this timestamp is committed. The frozen wrapper
                # preserves the certified model's exact-timestamp semantics.
                featured_group = wrapper.feature_group(group)
                featured_by_id = {
                    str(row["transaction_id"]): featured
                    for row, featured in zip(group, featured_group, strict=True)
                }

                for target in targets_here:
                    target_id = str(target["transaction_id"])
                    features = featured_by_id[target_id]["features"]

                    missing = [
                        name for name in feature_names if name not in features
                    ]
                    extras = [
                        name for name in features if name not in feature_names
                    ]
                    if missing or extras:
                        raise RuntimeError(
                            "historical feature schema mismatch: "
                            f"missing={missing}, extras={extras}"
                        )

                    raw_score, calibrated_score = _score_feature_vector(
                        features,
                        model,
                        bundle,
                        feature_names,
                        categorical_features,
                    )

                    gold = _certified_gold_features(target_id, feature_names)
                    mismatches = [
                        {
                            "index": index,
                            "feature": name,
                            "historical_replay": features[name],
                            "certified_gold": gold[name],
                        }
                        for index, name in enumerate(feature_names)
                        if not _same_value(features[name], gold[name])
                    ]

                    reference = CERTIFIED_REFERENCES.get(target_id)
                    reference_match = None
                    if reference is not None:
                        reference_match = {
                            "raw_model_score": math.isclose(
                                raw_score,
                                reference["raw_model_score"],
                                rel_tol=0.0,
                                abs_tol=1e-15,
                            ),
                            "calibrated_score": math.isclose(
                                calibrated_score,
                                reference["calibrated_score"],
                                rel_tol=0.0,
                                abs_tol=1e-15,
                            ),
                        }

                    results.append(
                        {
                            "transaction_id": target_id,
                            "event_ts": (
                                target["event_ts"].isoformat()
                                if isinstance(target["event_ts"], datetime)
                                else str(target["event_ts"])
                            ),
                            "replayed_row_count": history_counts[target_id],
                            "replayed_rows_committed_before_target": committed_rows,
                            "replayed_timestamp_groups_before_target": committed_groups,
                            "feature_count": len(feature_names),
                            "feature_vector": {
                                name: features[name] for name in feature_names
                            },
                            "feature_order": feature_names,
                            "feature_mismatch_count_vs_certified_gold": len(
                                mismatches
                            ),
                            "feature_mismatches_vs_certified_gold": mismatches,
                            "raw_model_score": raw_score,
                            "calibrated_score": calibrated_score,
                            "certified_reference": reference,
                            "certified_reference_match": reference_match,
                            "target_featured_before_same_timestamp_commit": True,
                        }
                    )

            # Advance only after recording all targets at this timestamp.
            # Mode B bypasses GuardedLiveStateWriter by design and delegates
            # directly to the unchanged certified Engine.
            wrapper.engine.commit_group(group)
            committed_rows += len(group)
            committed_groups += 1

        status = "PASS"
        for result in results:
            if result["feature_mismatch_count_vs_certified_gold"] != 0:
                status = "FAIL"
            reference_match = result["certified_reference_match"]
            if reference_match is not None and not all(reference_match.values()):
                status = "FAIL"

        if cleanup_after:
            cleanup_deleted_keys = wrapper.clear()

        payload = {
            "status": status,
            "mode": "historical_pit_certification_only",
            "live_api_involved": False,
            "public_endpoint": False,
            "namespace": namespace,
            "namespace_cleared_before": bool(clear_namespace),
            "namespace_keys_removed_before": cleared_before,
            "cleanup_after": bool(cleanup_after),
            "cleanup_deleted_keys": cleanup_deleted_keys,
            "target_count": len(targets),
            "targets_requested": target_ids,
            "targets_sorted_by_event_ts": [
                str(target["transaction_id"]) for target in targets
            ],
            "model_feature_count": len(feature_names),
            "strict_point_in_time": True,
            "target_featured_before_same_timestamp_commit": True,
            "union_replay_rows_including_targets": len(stream),
            "final_committed_rows": committed_rows,
            "final_committed_timestamp_groups": committed_groups,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "targets": results,
        }

        if output_path is not None:
            path = Path(output_path)
            if not path.is_absolute():
                path = ROOT / path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, indent=2, default=str),
                encoding="utf-8",
            )
            payload["evidence_path"] = str(path)

        return payload
    except Exception:
        if cleanup_after:
            wrapper.clear()
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "GraphShield historical point-in-time replay for "
            "certification evidence only."
        )
    )
    parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        default=None,
        help="Target transaction ID. Repeat for multiple targets.",
    )
    parser.add_argument(
        "--redis-url",
        default=(
            os.getenv("GS_HISTORICAL_REPLAY_REDIS_URL")
            or DEFAULT_REDIS_URL
        ),
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
    )
    parser.add_argument(
        "--keep-namespace",
        action="store_true",
        help=(
            "Keep the final target's temporary certification state "
            "instead of cleaning it."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_historical_replay(
        target_ids=args.targets or DEFAULT_TARGET_IDS,
        redis_url=args.redis_url,
        namespace=args.namespace,
        output_path=args.output,
        clear_namespace=True,
        cleanup_after=not args.keep_namespace,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
