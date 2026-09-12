from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from explainability.explanation_service import Phase11ExplanationService


TEMPORAL_FEATURES = [
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "sender_prior_tx_count",
    "sender_prior_amount_sum",
    "sender_prior_amount_avg",
    "sender_seconds_since_previous",
    "receiver_prior_tx_count",
    "receiver_prior_amount_sum",
    "receiver_prior_amount_avg",
    "receiver_seconds_since_previous",
    "sender_tx_count_1h",
    "sender_tx_count_24h",
    "sender_tx_count_7d",
    "receiver_tx_count_1h",
    "receiver_tx_count_24h",
    "receiver_tx_count_7d",
    "sender_unique_receivers_1h",
    "sender_unique_receivers_24h",
    "sender_unique_receivers_7d",
    "receiver_unique_senders_1h",
    "receiver_unique_senders_24h",
    "receiver_unique_senders_7d",
    "sender_fanout_ratio_1h",
    "sender_fanout_ratio_24h",
    "receiver_fanin_ratio_1h",
    "receiver_fanin_ratio_24h",
    "sender_recent_inbound_count_1h",
    "sender_recent_inbound_count_24h",
    "recent_inbound_coverage_1h",
    "seconds_since_last_inbound_1h",
    "rapid_pass_through_candidate",
]


def _safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


class Phase11TemporalEvidenceService:
    """
    Read-only temporal explanation layer.

    It does NOT claim SHAP attribution for the TGN.
    Instead it exposes:
      - the frozen Phase 10 TGN component score;
      - certified point-in-time temporal/history/velocity features;
      - deterministic temporal interpretation flags.
    """

    def __init__(self) -> None:
        self.explanations = Phase11ExplanationService()

    def explain_temporal(
        self,
        transaction_id: str,
    ) -> dict[str, Any]:
        explanation = self.explanations.explain_transaction(
            transaction_id=transaction_id,
            top_k=8,
        )

        row = self.explanations._load_feature_row(
            transaction_id
        )

        snapshot = {
            name: _safe(row.get(name))
            for name in TEMPORAL_FEATURES
            if name in row
        }

        rapid = bool(
            row.get("rapid_pass_through_candidate")
            in (1, True)
        )

        recent_inbound = int(
            row.get("sender_recent_inbound_count_1h")
            or 0
        )

        sender_1h = int(
            row.get("sender_tx_count_1h")
            or 0
        )

        receiver_1h = int(
            row.get("receiver_tx_count_1h")
            or 0
        )

        temporal_observations = []

        if rapid:
            temporal_observations.append(
                {
                    "code": "GS_TEMPORAL_RAPID_PASS_THROUGH",
                    "title": "Rapid pass-through temporal signal",
                    "source": "certified_phase10_feature_store",
                }
            )

        if recent_inbound > 0:
            temporal_observations.append(
                {
                    "code": "GS_TEMPORAL_RECENT_INBOUND",
                    "title": "Recent inbound activity before focal transfer",
                    "value": recent_inbound,
                    "window": "1h",
                    "source": "certified_phase10_feature_store",
                }
            )

        if sender_1h > 0:
            temporal_observations.append(
                {
                    "code": "GS_TEMPORAL_SENDER_ACTIVITY_1H",
                    "title": "Sender activity observed in prior 1h window",
                    "value": sender_1h,
                    "source": "certified_phase10_feature_store",
                }
            )

        if receiver_1h > 0:
            temporal_observations.append(
                {
                    "code": "GS_TEMPORAL_RECEIVER_ACTIVITY_1H",
                    "title": "Receiver activity observed in prior 1h window",
                    "value": receiver_1h,
                    "source": "certified_phase10_feature_store",
                }
            )

        temporal_model = explanation.get(
            "temporal_model"
        )

        return {
            "transaction_id": str(transaction_id),
            "event_ts": explanation.get("event_ts"),
            "phase10_final_candidate": explanation.get(
                "phase10_final_candidate"
            ),
            "tgn_component": temporal_model,
            "temporal_feature_snapshot": snapshot,
            "temporal_observations": temporal_observations,
            "interpretation_contract": {
                "tgn_score_is_component_score": True,
                "tgn_score_is_not_tree_shap": True,
                "point_in_time_features_only": True,
                "current_event_not_used_as_history": True,
                "ground_truth_label_exposed": False,
            },
            "governance": explanation["governance"],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--transaction-id",
        required=True,
    )
    args = parser.parse_args()

    result = Phase11TemporalEvidenceService().explain_temporal(
        args.transaction_id
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
