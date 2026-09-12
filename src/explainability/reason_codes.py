from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from explainability.explanation_service import Phase11ExplanationService


BINARY_REASON_RULES = {
    "rapid_pass_through_candidate": {
        "code": "GS_RAPID_PASS_THROUGH",
        "category": "temporal_flow",
        "title": "Rapid pass-through pattern",
        "description": (
            "The certified point-in-time feature indicates recent inbound "
            "activity followed by a qualifying outbound transfer pattern."
        ),
    },
    "reciprocal_prior_exists": {
        "code": "GS_RECIPROCAL_RELATIONSHIP",
        "category": "graph_relationship",
        "title": "Prior reciprocal relationship",
        "description": (
            "The reverse directed account pair had prior transaction history "
            "before the focal transaction."
        ),
    },
    "closes_two_node_cycle": {
        "code": "GS_TWO_NODE_CYCLE",
        "category": "graph_motif",
        "title": "Two-node cycle signal",
        "description": (
            "The focal direction closes a previously observed reciprocal "
            "two-account transaction pattern."
        ),
    },
    "graph_new_pair": {
        "code": "GS_NEW_PAIR",
        "category": "counterparty",
        "title": "New directed counterparty pair",
        "description": (
            "No prior transaction was observed for this directed sender-to-"
            "receiver pair before the focal event."
        ),
    },
    "graph_established_pair": {
        "code": "GS_ESTABLISHED_PAIR",
        "category": "counterparty",
        "title": "Established directed pair",
        "description": (
            "The directed sender-to-receiver relationship had reached the "
            "certified established-pair condition before the focal event."
        ),
    },
    "new_receiver_for_sender": {
        "code": "GS_NEW_RECEIVER_FOR_SENDER",
        "category": "counterparty",
        "title": "New receiver for sender",
        "description": (
            "The receiver is new in the sender's prior point-in-time "
            "counterparty history."
        ),
    },
    "new_sender_for_receiver": {
        "code": "GS_NEW_SENDER_FOR_RECEIVER",
        "category": "counterparty",
        "title": "New sender for receiver",
        "description": (
            "The sender is new in the receiver's prior point-in-time "
            "counterparty history."
        ),
    },
    "cross_bank": {
        "code": "GS_CROSS_BANK",
        "category": "transaction",
        "title": "Cross-bank transfer",
        "description": (
            "The sending and receiving banks differ for the focal transaction."
        ),
    },
    "cross_currency": {
        "code": "GS_CROSS_CURRENCY",
        "category": "transaction",
        "title": "Cross-currency transfer",
        "description": (
            "The payment and receiving currencies differ for the focal "
            "transaction."
        ),
    },
}


FEATURE_FAMILY_PREFIXES = [
    ("pair_", "pair_history"),
    ("reverse_pair_", "reciprocal_history"),
    ("sender_", "sender_behavior"),
    ("receiver_", "receiver_behavior"),
    ("bank_pair_", "bank_graph"),
    ("graph_", "graph_relationship"),
]


def feature_family(name: str) -> str:
    if name in {
        "reciprocal_prior_exists",
        "closes_two_node_cycle",
        "directional_history_balance",
    }:
        return "graph_motif"

    if name in {
        "rapid_pass_through_candidate",
        "recent_inbound_coverage_1h",
        "seconds_since_last_inbound_1h",
        "sender_recent_inbound_count_1h",
        "sender_recent_inbound_count_24h",
    }:
        return "temporal_flow"

    if name in {
        "amount_paid",
        "amount_received",
        "payment_format",
        "payment_currency",
        "receiving_currency",
        "cross_bank",
        "cross_currency",
        "same_currency_amount_ratio",
    }:
        return "transaction"

    for prefix, family in FEATURE_FAMILY_PREFIXES:
        if name.startswith(prefix):
            return family

    return "other"


class Phase11ReasonCodeService:
    """
    Deterministic reason-code layer over Phase 11 explanation output.

    Two evidence classes are kept separate:
    1. observed_signals: feature-state rules with explicit semantics;
    2. model_drivers: TreeSHAP drivers from the frozen LightGBM graph model.

    No ground-truth label is consumed or exposed.
    """

    def __init__(self) -> None:
        self.explanations = Phase11ExplanationService()

    @staticmethod
    def _binary_is_active(value: Any) -> bool:
        if value is None:
            return False

        if isinstance(value, bool):
            return value

        try:
            return float(value) == 1.0
        except (TypeError, ValueError):
            return False

    def build_reason_codes(
        self,
        transaction_id: str,
        top_k_drivers: int = 8,
    ) -> dict[str, Any]:
        explanation = self.explanations.explain_transaction(
            transaction_id=transaction_id,
            top_k=top_k_drivers,
        )

        graph_model = explanation["graph_model"]

        # Reconstruct a feature->value map from both positive and negative
        # SHAP lists. For binary semantic reason codes not present in the
        # top-K SHAP lists, load the exact certified feature row directly.
        feature_row = self.explanations._load_feature_row(
            transaction_id
        )

        observed_signals: list[dict[str, Any]] = []

        for feature, rule in BINARY_REASON_RULES.items():
            value = feature_row.get(feature)

            if not self._binary_is_active(value):
                continue

            observed_signals.append(
                {
                    "reason_code": rule["code"],
                    "reason_type": "observed_feature_signal",
                    "category": rule["category"],
                    "title": rule["title"],
                    "description": rule["description"],
                    "feature": feature,
                    "feature_value": value,
                    "evidence_origin": "certified_phase10_feature_store",
                    "model_dependency": False,
                }
            )

        model_drivers: list[dict[str, Any]] = []

        for item in graph_model["top_risk_raising_features"]:
            model_drivers.append(
                {
                    "reason_code": (
                        "GS_MODEL_DRIVER_"
                        + item["feature"].upper()
                    ),
                    "reason_type": "model_driver",
                    "category": feature_family(
                        item["feature"]
                    ),
                    "title": (
                        "Model risk driver: "
                        + item["feature"]
                    ),
                    "feature": item["feature"],
                    "feature_value": item["feature_value"],
                    "shap_value_raw_margin": item[
                        "shap_value_raw_margin"
                    ],
                    "rank": item["rank"],
                    "direction": "raises_risk",
                    "evidence_origin": "frozen_lightgbm_tree_shap",
                    "model_dependency": True,
                }
            )

        protective_drivers: list[dict[str, Any]] = []

        for item in graph_model["top_risk_lowering_features"]:
            protective_drivers.append(
                {
                    "reason_code": (
                        "GS_PROTECTIVE_DRIVER_"
                        + item["feature"].upper()
                    ),
                    "reason_type": "model_driver",
                    "category": feature_family(
                        item["feature"]
                    ),
                    "title": (
                        "Model risk-lowering driver: "
                        + item["feature"]
                    ),
                    "feature": item["feature"],
                    "feature_value": item["feature_value"],
                    "shap_value_raw_margin": item[
                        "shap_value_raw_margin"
                    ],
                    "rank": item["rank"],
                    "direction": "lowers_risk",
                    "evidence_origin": "frozen_lightgbm_tree_shap",
                    "model_dependency": True,
                }
            )

        return {
            "transaction_id": explanation["transaction_id"],
            "event_ts": explanation["event_ts"],
            "phase10_final_candidate": explanation[
                "phase10_final_candidate"
            ],
            "scores": {
                "graph_score_raw": graph_model["score_raw"],
                "graph_score_calibrated": graph_model[
                    "score_calibrated"
                ],
                "tgn_risk_score": (
                    explanation["temporal_model"][
                        "tgn_risk_score"
                    ]
                    if explanation["temporal_model"]
                    else None
                ),
                "fusion_score_raw": (
                    explanation["fusion"][
                        "fusion_score_raw"
                    ]
                    if explanation["fusion"]
                    else None
                ),
                "fusion_score_calibrated": (
                    explanation["fusion"][
                        "fusion_score_calibrated"
                    ]
                    if explanation["fusion"]
                    else None
                ),
            },
            "observed_signals": observed_signals,
            "model_risk_drivers": model_drivers,
            "model_protective_drivers": protective_drivers,
            "reason_code_counts": {
                "observed_signals": len(observed_signals),
                "risk_drivers": len(model_drivers),
                "protective_drivers": len(
                    protective_drivers
                ),
            },
            "interpretation_contract": {
                "observed_signals_are_model_independent": True,
                "model_drivers_are_tree_shap_attributions": True,
                "tree_shap_space": "raw_margin",
                "tgn_is_not_shap_explained": True,
                "reason_codes_are_not_proof_of_wrongdoing": True,
            },
            "governance": explanation["governance"],
        }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--transaction-id",
        required=True,
    )

    parser.add_argument(
        "--top-k-drivers",
        type=int,
        default=8,
    )

    args = parser.parse_args()

    service = Phase11ReasonCodeService()

    result = service.build_reason_codes(
        transaction_id=args.transaction_id,
        top_k_drivers=args.top_k_drivers,
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

