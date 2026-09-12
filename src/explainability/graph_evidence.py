from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from explainability.explanation_service import (
    Phase11ExplanationService,
)
from explainability.reason_codes import (
    Phase11ReasonCodeService,
)

from services.case_graph_service import (
    CaseGraphService,
)
from services.graphshield_service import (
    GraphShieldService,
)


CASE_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)


GRAPH_FEATURES = [
    "sender_prior_unique_receivers",
    "receiver_prior_unique_senders",
    "pair_prior_tx_count",
    "pair_prior_amount_sum",
    "pair_prior_amount_avg",
    "pair_seconds_since_previous",
    "pair_relationship_age_seconds",
    "pair_share_of_sender_history",
    "pair_share_of_receiver_history",
    "graph_new_pair",
    "graph_established_pair",
    "bank_pair_prior_tx_count",
    "bank_pair_prior_amount_sum",
    "bank_pair_prior_amount_avg",
    "sender_bank_prior_tx_count",
    "bank_pair_share_of_sender_bank_history",
    "reverse_pair_prior_tx_count",
    "reverse_pair_prior_amount_sum",
    "reverse_pair_seconds_since_previous",
    "reciprocal_prior_exists",
    "closes_two_node_cycle",
    "directional_history_balance",
    "sender_prior_unique_senders",
    "receiver_prior_unique_receivers",
    "sender_bridge_degree",
    "receiver_bridge_degree",
]


def _json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def _resolve_case_id(
    transaction_id: str,
) -> str | None:
    if not CASE_QUEUE_PATH.exists():
        return None

    schema = pl.read_parquet_schema(
        CASE_QUEUE_PATH
    )
    names = set(schema.names())

    if "transaction_id" not in names:
        return None

    case_column = None

    for candidate in (
        "case_id",
        "investigation_id",
        "alert_id",
    ):
        if candidate in names:
            case_column = candidate
            break

    if case_column is None:
        return None

    row = (
        pl.scan_parquet(
            CASE_QUEUE_PATH
        )
        .filter(
            pl.col("transaction_id")
            .cast(pl.String)
            == str(transaction_id)
        )
        .select(
            pl.col(case_column)
            .cast(pl.String)
            .alias("case_id")
        )
        .head(1)
        .collect()
    )

    if row.height == 0:
        return None

    return str(
        row.get_column(
            "case_id"
        )[0]
    )


def _compact_path_evidence(
    documents: list[dict[str, Any]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    result = []

    for item in documents[:limit]:
        result.append(
            {
                "evidence_id": item.get(
                    "evidence_id"
                ),
                "source_type": item.get(
                    "source_type"
                ),
                "source_ref": item.get(
                    "source_ref"
                ),
                "content": item.get(
                    "content"
                ),
            }
        )

    return result


class Phase11GraphEvidenceService:
    """
    Read-only graph evidence explanation over frozen Phase 10 artifacts.

    This layer separates:
      1. point-in-time graph feature facts;
      2. deterministic graph/motif reason codes;
      3. materialized investigation graph evidence;
      4. graph-path evidence.

    It never consumes or exposes the ground-truth laundering label.
    """

    def __init__(self) -> None:
        self.explanations = (
            Phase11ExplanationService()
        )

        self.reason_codes = (
            Phase11ReasonCodeService()
        )

        self._case_graph = None
        self._graphshield = None

    def _graph_feature_snapshot(
        self,
        transaction_id: str,
    ) -> dict[str, Any]:
        row = (
            self.explanations
            ._load_feature_row(
                transaction_id
            )
        )

        return {
            name: _json_safe(
                row.get(name)
            )
            for name in GRAPH_FEATURES
        }

    def _graph_reason_signals(
        self,
        transaction_id: str,
    ) -> list[dict[str, Any]]:
        reasons = (
            self.reason_codes
            .build_reason_codes(
                transaction_id=
                    transaction_id,
                top_k_drivers=8,
            )
        )

        graph_categories = {
            "graph_relationship",
            "graph_motif",
            "pair_history",
            "reciprocal_history",
            "bank_graph",
            "counterparty",
        }

        observed = [
            item
            for item in reasons[
                "observed_signals"
            ]
            if item.get(
                "category"
            )
            in graph_categories
        ]

        model_drivers = [
            item
            for item in reasons[
                "model_risk_drivers"
            ]
            if item.get(
                "category"
            )
            in graph_categories
        ]

        protective_drivers = [
            item
            for item in reasons[
                "model_protective_drivers"
            ]
            if item.get(
                "category"
            )
            in graph_categories
        ]

        return [
            *observed,
            *model_drivers,
            *protective_drivers,
        ]

    def _materialized_graph(
        self,
        case_id: str | None,
    ) -> dict[str, Any]:
        if not case_id:
            return {
                "available": False,
                "reason": (
                    "Transaction is not mapped "
                    "to a materialized case."
                ),
            }

        try:
            if self._case_graph is None:
                self._case_graph = (
                    CaseGraphService()
                )

            graph = (
                self._case_graph
                .get_graph(
                    case_id=case_id,
                    max_edges=200,
                )
            )

            return {
                "available": True,
                "case_id": case_id,
                "focal_transaction_id":
                    graph.get(
                        "focal_transaction_id"
                    ),
                "displayed_nodes":
                    graph.get(
                        "displayed_nodes"
                    ),
                "displayed_edges":
                    graph.get(
                        "displayed_edges"
                    ),
                "total_subgraph_edges":
                    graph.get(
                        "total_subgraph_edges"
                    ),
                "source_column":
                    graph.get(
                        "source_column"
                    ),
                "target_column":
                    graph.get(
                        "target_column"
                    ),
            }

        except FileNotFoundError:
            return {
                "available": False,
                "case_id": case_id,
                "reason": (
                    "Case exists but its investigation "
                    "graph is not currently materialized."
                ),
            }

    def _path_evidence(
        self,
        case_id: str | None,
    ) -> list[dict[str, Any]]:
        if not case_id:
            return []

        try:
            if self._graphshield is None:
                self._graphshield = (
                    GraphShieldService(
                        enable_policy_reranker=False
                    )
                )

            documents = (
                self._graphshield
                .path_evidence(
                    case_id
                )
            )

            return _compact_path_evidence(
                documents,
                limit=8,
            )

        except FileNotFoundError:
            return []

    def explain_graph(
        self,
        transaction_id: str,
    ) -> dict[str, Any]:
        explanation = (
            self.explanations
            .explain_transaction(
                transaction_id=
                    transaction_id,
                top_k=8,
            )
        )

        case_id = _resolve_case_id(
            transaction_id
        )

        snapshot = (
            self._graph_feature_snapshot(
                transaction_id
            )
        )

        signals = (
            self._graph_reason_signals(
                transaction_id
            )
        )

        graph = (
            self._materialized_graph(
                case_id
            )
        )

        paths = (
            self._path_evidence(
                case_id
            )
        )

        return {
            "transaction_id":
                transaction_id,

            "event_ts":
                explanation.get(
                    "event_ts"
                ),

            "case_id":
                case_id,

            "phase10_final_candidate":
                explanation.get(
                    "phase10_final_candidate"
                ),

            "graph_feature_snapshot":
                snapshot,

            "graph_explanation_signals":
                signals,

            "investigation_graph":
                graph,

            "path_evidence":
                paths,

            "evidence_summary": {
                "graph_feature_count":
                    len(
                        GRAPH_FEATURES
                    ),

                "graph_signal_count":
                    len(
                        signals
                    ),

                "path_evidence_count":
                    len(
                        paths
                    ),

                "materialized_graph_available":
                    bool(
                        graph.get(
                            "available"
                        )
                    ),
            },

            "interpretation_contract": {
                "point_in_time_graph_features":
                    True,

                "graph_signals_are_not_proof":
                    True,

                "tree_shap_and_graph_facts_kept_separate":
                    True,

                "ground_truth_label_exposed":
                    False,
            },

            "governance": {
                "mode":
                    "decision_support_only",

                "human_review_required":
                    True,

                "certified_phase10_artifacts":
                    "read_only",

                "autonomous_account_blocking":
                    False,

                "autonomous_case_closure":
                    False,

                "autonomous_regulatory_filing":
                    False,
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--transaction-id",
        required=True,
    )

    args = parser.parse_args()

    service = (
        Phase11GraphEvidenceService()
    )

    result = (
        service.explain_graph(
            transaction_id=
                args.transaction_id
        )
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
