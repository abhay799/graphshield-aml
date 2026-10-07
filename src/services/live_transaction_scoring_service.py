from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from services.guarded_live_state_writer import GuardedLiveStateWriter
from services.live_scoring_feature_wrapper import FrozenModelFeatureWrapper
from streaming.phase10_b3_online_feature_parity import normalize

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "models" / "lightgbm_graph_v1.joblib"
CALIBRATOR_PATH = ROOT / "models" / "probability_calibrator_graph_v1.joblib"
CONTRACT_PATH = ROOT / "reports" / "v2" / "phase10" / "live_feature_contract_v1.json"

SCORING_MODE = "live_research_only"
BOUNDARY_FLAG = "synthetic_research_demo_only"


class LiveTransactionScoringService:
    """Stateful Redis-backed scorer; canonical GraphShield artifacts remain immutable."""

    def __init__(
        self,
        redis_url: str | None = None,
        namespace: str | None = None,
    ) -> None:
        self.redis_url = redis_url or os.getenv(
            "GS_LIVE_SCORING_REDIS_URL", "redis://127.0.0.1:6379/0"
        )
        self.namespace = namespace or os.getenv(
            "GS_LIVE_SCORING_NAMESPACE", "gs:live:scoring:v1"
        )
        self.wrapper = FrozenModelFeatureWrapper(self.redis_url, self.namespace)
        self.state_writer = GuardedLiveStateWriter(self.wrapper, self.namespace)

        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.model = joblib.load(MODEL_PATH)
        self.calibration_bundle = joblib.load(CALIBRATOR_PATH)
        self._validate_model_contract()

        self.feature_names = list(self.calibration_bundle["feature_names"])
        self.categorical_features = list(
            self.calibration_bundle.get("categorical_features", [])
        )
        self.calibrator = self.calibration_bundle["calibrator"]

    def _validate_model_contract(self) -> None:
        if self.contract.get("status") != "PASS":
            raise RuntimeError("Live feature contract is not certified PASS.")
        if self.contract.get("label_leakage_allowed") is not False:
            raise RuntimeError("Live feature contract permits label leakage.")
        if self.contract.get("label_like_features") not in ([], None):
            raise RuntimeError("Live feature contract contains label-like features.")
        if self.contract.get("require_exact_online_parity") is not True:
            raise RuntimeError("Live feature contract does not require exact parity.")

        contract_features = list(self.contract.get("model_features", []))
        model_features = list(getattr(self.model, "feature_name_", []))
        calibrator_features = list(
            self.calibration_bundle.get("feature_names", [])
        )

        if not contract_features or len(contract_features) != 70:
            raise RuntimeError("Live model contract must contain exactly 70 features.")
        if model_features != contract_features:
            raise RuntimeError(
                "Frozen LightGBM schema does not match the live feature contract."
            )
        if calibrator_features != contract_features:
            raise RuntimeError(
                "Calibration artifact schema does not match the live feature contract."
            )
        if self.calibration_bundle.get("method") != "platt_logit":
            raise RuntimeError("Unexpected calibration method.")
        if "calibrator" not in self.calibration_bundle:
            raise RuntimeError("Calibration artifact is missing its calibrator.")

    def _account_known(self, account_key: str) -> bool:
        # "Known" means Redis contained pre-existing transaction history for the
        # account in either role before the current transaction is scored.
        sender_count = self.wrapper.engine.hi(
            self.wrapper.engine.h("sender_hist", account_key), "tx_count"
        )
        receiver_count = self.wrapper.engine.hi(
            self.wrapper.engine.h("receiver_hist", account_key), "tx_count"
        )
        return (sender_count + receiver_count) > 0

    def _model_frame(self, features: dict[str, Any]) -> pd.DataFrame:
        row = {name: features.get(name) for name in self.feature_names}
        frame = pd.DataFrame([row], columns=self.feature_names)

        for name in self.feature_names:
            if name in self.categorical_features:
                frame[name] = (
                    frame[name]
                    .fillna("__MISSING__")
                    .astype("string")
                    .astype("category")
                )
            else:
                frame[name] = pd.to_numeric(frame[name], errors="coerce").astype(
                    "float32"
                )
        return frame

    @staticmethod
    def _feature_breakdown(features: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Group the frozen 70 model inputs for UI inspection without recomputing them."""
        transaction_names = (
            "amount_paid", "amount_received", "log_amount_paid",
            "log_amount_received", "payment_format", "payment_currency",
            "receiving_currency", "hour_of_day", "day_of_week", "is_weekend",
            "cross_bank", "cross_currency", "same_currency_amount_ratio",
        )
        pass_through_names = (
            "sender_recent_inbound_count_1h",
            "sender_recent_inbound_count_24h",
            "recent_inbound_coverage_1h",
            "seconds_since_last_inbound_1h",
            "rapid_pass_through_candidate",
        )
        network_names = (
            "graph_new_pair", "graph_established_pair",
            "bank_pair_prior_tx_count", "bank_pair_prior_amount_sum",
            "bank_pair_prior_amount_avg", "sender_bank_prior_tx_count",
            "bank_pair_share_of_sender_bank_history",
            "reverse_pair_prior_tx_count", "reverse_pair_prior_amount_sum",
            "reverse_pair_seconds_since_previous", "reciprocal_prior_exists",
            "closes_two_node_cycle", "directional_history_balance",
            "sender_prior_unique_senders", "receiver_prior_unique_receivers",
            "sender_bridge_degree", "receiver_bridge_degree",
        )
        assigned = set(transaction_names) | set(pass_through_names) | set(network_names)
        history_names = tuple(name for name in features if name not in assigned)

        groups = {
            "transaction": transaction_names,
            "history": history_names,
            "network": network_names,
            "pass_through": pass_through_names,
        }
        breakdown = {
            group: {name: features.get(name) for name in names}
            for group, names in groups.items()
        }

        flattened = [name for group in breakdown.values() for name in group]
        if len(flattened) != len(features) or set(flattened) != set(features):
            raise RuntimeError("Feature breakdown does not cover the frozen model vector.")
        return breakdown

    @staticmethod
    def _logit(probability: float) -> float:
        p = float(np.clip(probability, 1e-6, 1 - 1e-6))
        return math.log(p / (1.0 - p))

    def score_transaction(
        self,
        raw: dict[str, Any],
        *,
        commit_runtime_state: bool = True,
    ) -> dict[str, Any]:
        event = normalize(raw)
        sender = event["from_account_key"]
        receiver = event["to_account_key"]

        sender_known = self._account_known(sender)
        receiver_known = self._account_known(receiver)

        featured = self.wrapper.feature(raw)
        features = featured["features"]

        if list(features.keys()) != self.feature_names:
            # Dict insertion order is not the contract; construct by explicit
            # frozen feature_names below. This guard is only cardinality/schema.
            missing = [x for x in self.feature_names if x not in features]
            extras = [x for x in features if x not in self.feature_names]
            if missing or extras:
                raise RuntimeError(
                    f"Live feature schema mismatch: missing={missing}, extras={extras}"
                )

        frame = self._model_frame(features)
        raw_probability = float(self.model.predict_proba(frame)[0, 1])
        calibrated_score = float(
            self.calibrator.predict_proba(
                np.asarray([[self._logit(raw_probability)]], dtype=float)
            )[0, 1]
        )

        if commit_runtime_state:
            # Redis-only mutation. Mode A is forward-only: the guarded writer
            # rejects historical or duplicate writes before delegating to the
            # unchanged certified wrapper/Engine.
            self.state_writer.commit_group([raw])

        limited = not (sender_known and receiver_known)
        return {
            "transaction_id": event["transaction_id"],
            "calibrated_score": calibrated_score,
            "raw_model_score": raw_probability,
            "account_history": {
                "sender": "known" if sender_known else "unknown",
                "receiver": "known" if receiver_known else "unknown",
            },
            "limited_signal": limited,
            "limitation_note": (
                "Structurally limited signal: network/history-based signals "
                "are unavailable or incomplete for first-time accounts."
                if limited
                else None
            ),
            "scoring_mode": SCORING_MODE,
            "boundary": BOUNDARY_FLAG,
            "boundary_note": (
                "Synthetic/research demo only — not real fraud detection, "
                "not an enforcement or compliance decision."
            ),
            "synthetic_research_demo_only": True,
            "runtime_state_updated": bool(commit_runtime_state),
            "canonical_artifacts_modified": False,
            "feature_breakdown": self._feature_breakdown(features),
        }