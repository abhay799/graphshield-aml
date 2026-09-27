#!/usr/bin/env python3
"""Create deterministic, disposable CI artifacts for the test suite.

This program is intentionally fail-closed outside GitHub Actions: it never
overwrites a pre-existing runtime artifact on a developer machine.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import numpy as np
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer

from tests.fixtures.ci_model_stubs import DeterministicCalibrator, DeterministicGraphModel

DATA_ROOT = PROJECT_ROOT / "data"
CASE_QUEUE_PATH = DATA_ROOT / "processed" / "cases" / "case_queue.parquet"
EVIDENCE_PATH = DATA_ROOT / "processed" / "cases" / "evidence_documents.parquet"
EVIDENCE_INDEX_PATH = DATA_ROOT / "processed" / "cases" / "evidence_tfidf_index.joblib"
SUBGRAPH_PATH = DATA_ROOT / "processed" / "cases" / "subgraphs" / "CASE_IBM_LI_SMALL_4310302.parquet"
MODEL_FEATURES_PATH = DATA_ROOT / "processed" / "gold" / "model_features_v2_graph_split.parquet"
PHASE10_PREDICTIONS_PATH = DATA_ROOT / "processed" / "modeling" / "v2" / "phase10" / "locked_test_predictions_v1.parquet"
LIGHTGBM_MODEL_PATH = PROJECT_ROOT / "models" / "lightgbm_graph_v1.joblib"
CALIBRATOR_PATH = PROJECT_ROOT / "models" / "probability_calibrator_graph_v1.joblib"

# Actual Phase 11 temporal, reason-code, and graph fields consumed by the
# explanation services; no placeholder feature_0-style names are used.
FEATURE_NAMES = [
    "amount_paid", "amount_received", "cross_bank", "cross_currency",
    "rapid_pass_through_candidate", "new_receiver_for_sender", "new_sender_for_receiver",
    "graph_new_pair", "graph_established_pair", "reciprocal_prior_exists",
    "closes_two_node_cycle", "hour_of_day", "day_of_week", "is_weekend",
    "sender_prior_tx_count", "sender_prior_amount_sum", "sender_prior_amount_avg",
    "sender_seconds_since_previous", "receiver_prior_tx_count", "receiver_prior_amount_sum",
    "receiver_prior_amount_avg", "receiver_seconds_since_previous", "sender_tx_count_1h",
    "sender_tx_count_24h", "sender_tx_count_7d", "receiver_tx_count_1h",
    "receiver_tx_count_24h", "receiver_tx_count_7d", "sender_unique_receivers_1h",
    "sender_unique_receivers_24h", "sender_unique_receivers_7d", "receiver_unique_senders_1h",
    "receiver_unique_senders_24h", "receiver_unique_senders_7d", "sender_fanout_ratio_1h",
    "sender_fanout_ratio_24h", "receiver_fanin_ratio_1h", "receiver_fanin_ratio_24h",
    "sender_recent_inbound_count_1h", "sender_recent_inbound_count_24h",
    "recent_inbound_coverage_1h", "seconds_since_last_inbound_1h",
    "sender_prior_unique_receivers", "receiver_prior_unique_senders", "pair_prior_tx_count",
    "pair_prior_amount_sum", "pair_prior_amount_avg", "pair_seconds_since_previous",
    "pair_relationship_age_seconds", "pair_share_of_sender_history", "pair_share_of_receiver_history",
    "bank_pair_prior_tx_count", "bank_pair_prior_amount_sum", "bank_pair_prior_amount_avg",
    "sender_bank_prior_tx_count", "bank_pair_share_of_sender_bank_history",
    "reverse_pair_prior_tx_count", "reverse_pair_prior_amount_sum",
    "reverse_pair_seconds_since_previous", "directional_history_balance",
    "sender_prior_unique_senders", "receiver_prior_unique_receivers", "sender_bridge_degree",
    "receiver_bridge_degree",
]

TARGETS = (CASE_QUEUE_PATH, EVIDENCE_PATH, EVIDENCE_INDEX_PATH, SUBGRAPH_PATH,
           MODEL_FEATURES_PATH, PHASE10_PREDICTIONS_PATH, LIGHTGBM_MODEL_PATH, CALIBRATOR_PATH)


def _in_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS", "").lower() == "true"


def _prepare(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def preflight() -> None:
    """Refuse local writes when a runtime target already exists."""
    if _in_github_actions():
        return
    existing = [str(path.relative_to(PROJECT_ROOT)) for path in TARGETS if path.exists()]
    if existing:
        raise RuntimeError(
            "Refusing to overwrite local runtime artifacts outside GitHub Actions: " + ", ".join(existing)
        )


def generate_case_queue() -> None:
    rows = []
    for index in range(7617):
        focal = index == 0
        rows.append({
            "risk_rank": index + 1,
            "case_id": "CASE_IBM_LI_SMALL_4310302" if focal else f"CASE_CI_{index:08d}",
            "transaction_id": "IBM_LI_SMALL_4310302" if focal else f"TX_CI_{index:08d}",
            "risk_score": 0.9999999999997846 if focal else 0.5 + index / 20000,
            "event_ts": "2022-09-09 03:22:00", "from_account_key": "ACC_ENT_18383_001",
            "to_account_key": "ACC_ENT_487964_001", "amount_paid": 12477.47,
            "payment_currency": "US Dollar", "payment_format": "ACH", "from_entity_id": "ENT_18383",
            "to_entity_id": "ENT_487964", "risk_percentile": 1.0, "source_model": "lightgbm_graph",
            "case_status": "OPEN",
        })
    _prepare(CASE_QUEUE_PATH)
    pl.DataFrame(rows).write_parquet(CASE_QUEUE_PATH)


def generate_evidence() -> None:
    case_id = "CASE_IBM_LI_SMALL_4310302"
    rows = [{"evidence_id": f"EVID_CI_{index:08d}", "case_id": case_id,
             "source_type": source_type, "source_ref": f"CI:{index}",
             "evidence_ts": "2022-09-09 03:22:00",
             "content": f"Deterministic CI evidence {index} for {source_type}.",
             "point_in_time_safe": True}
            for index, source_type in enumerate(("focal_transaction", "rule_evidence", "graph_summary", "graph_path", "historical_transactions"))]
    evidence = pl.DataFrame(rows)
    _prepare(EVIDENCE_PATH)
    evidence.write_parquet(EVIDENCE_PATH)
    vectorizer = TfidfVectorizer().fit(evidence["content"].to_list())
    _prepare(EVIDENCE_INDEX_PATH)
    joblib.dump({"vectorizer": vectorizer, "matrix": vectorizer.transform(evidence["content"].to_list()),
                 "evidence_ids": np.asarray(evidence["evidence_id"].to_list(), dtype=object),
                 "case_ids": np.asarray(evidence["case_id"].to_list(), dtype=object)}, EVIDENCE_INDEX_PATH)


def generate_subgraph() -> None:
    rows = [{
        "case_id": "CASE_IBM_LI_SMALL_4310302",
        "from_account_key": "ACC_ENT_18383_001",
        "to_account_key": "ACC_ENT_487964_001",
        "transaction_id": "IBM_LI_SMALL_4310302",
        "amount_paid": 12477.47,
        "event_ts": "2022-09-09 03:22:00",
    }]
    _prepare(SUBGRAPH_PATH)
    pl.DataFrame(rows).write_parquet(SUBGRAPH_PATH)


def generate_phase11_artifacts() -> None:
    rows = []
    for index in range(100):
        row = {name: float((index + position) % 7) for position, name in enumerate(FEATURE_NAMES)}
        row.update({"transaction_id": "IBM_LI_SMALL_4310302" if index == 0 else f"TX_CI_{index:08d}",
                    "event_ts": "2022-09-09 03:22:00", "split": "test"})
        rows.append(row)
    _prepare(MODEL_FEATURES_PATH)
    pl.DataFrame(rows).write_parquet(MODEL_FEATURES_PATH)
    predictions = pl.DataFrame([{"transaction_id": row["transaction_id"], "graph_score_raw": 0.8,
        "graph_score_calibrated": 0.8, "tgn_risk_score": 0.01, "graph_fixed_ecdf": 0.5,
        "tgn_fixed_ecdf": 0.5, "fusion_score_raw": 0.56, "fusion_score_calibrated": 0.45} for row in rows])
    _prepare(PHASE10_PREDICTIONS_PATH)
    predictions.write_parquet(PHASE10_PREDICTIONS_PATH)


def generate_model_artifacts() -> None:
    _prepare(LIGHTGBM_MODEL_PATH)
    joblib.dump(DeterministicGraphModel(FEATURE_NAMES), LIGHTGBM_MODEL_PATH)
    _prepare(CALIBRATOR_PATH)
    joblib.dump({"feature_names": FEATURE_NAMES, "categorical_features": [],
                 "calibrator": DeterministicCalibrator()}, CALIBRATOR_PATH)


def validate_artifacts() -> None:
    assert pl.read_parquet(CASE_QUEUE_PATH).height == 7617
    assert set(FEATURE_NAMES).issubset(pl.read_parquet_schema(MODEL_FEATURES_PATH).names())
    model, bundle = joblib.load(LIGHTGBM_MODEL_PATH), joblib.load(CALIBRATOR_PATH)
    assert model.feature_name_ == bundle["feature_names"]
    assert model.booster_.feature_name() == bundle["feature_names"]
    assert set(bundle) == {"feature_names", "categorical_features", "calibrator"}
    assert model.booster_.predict(np.zeros((1, len(FEATURE_NAMES))), pred_contrib=True).shape == (1, len(FEATURE_NAMES) + 1)
    subprocess.run([sys.executable, "-c", "import joblib; joblib.load('models/lightgbm_graph_v1.joblib'); joblib.load('models/probability_calibrator_graph_v1.joblib')"], cwd=PROJECT_ROOT, check=True)


def main() -> None:
    preflight()
    generate_case_queue()
    generate_evidence()
    generate_subgraph()
    generate_phase11_artifacts()
    generate_model_artifacts()
    validate_artifacts()
    print("CI test artifacts generated and self-validated.")


if __name__ == "__main__":
    main()
