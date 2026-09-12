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
from explainability.reason_codes import Phase11ReasonCodeService
from explainability.graph_evidence import Phase11GraphEvidenceService
from explainability.temporal_evidence import Phase11TemporalEvidenceService


class Phase11ExplanationBundleService:
    """
    Canonical Phase 11 explanation dossier.

    Combines model attribution, deterministic reason codes,
    graph evidence, and temporal evidence without mutating
    certified Phase 10 artifacts.
    """

    def __init__(self) -> None:
        self.model = Phase11ExplanationService()
        self.reasons = Phase11ReasonCodeService()
        self.graph = Phase11GraphEvidenceService()
        self.temporal = Phase11TemporalEvidenceService()

    def build(
        self,
        transaction_id: str,
        top_k: int = 8,
    ) -> dict[str, Any]:
        model = self.model.explain_transaction(
            transaction_id=transaction_id,
            top_k=top_k,
        )

        reasons = self.reasons.build_reason_codes(
            transaction_id=transaction_id,
            top_k_drivers=top_k,
        )

        graph = self.graph.explain_graph(
            transaction_id=transaction_id
        )

        temporal = self.temporal.explain_temporal(
            transaction_id=transaction_id
        )

        return {
            "schema_version": "phase11_explanation_bundle_v1",
            "transaction_id": str(transaction_id),
            "event_ts": model.get("event_ts"),
            "phase10_final_candidate": model.get(
                "phase10_final_candidate"
            ),
            "scores": reasons["scores"],
            "model_explanation": {
                "graph_model": model["graph_model"],
                "temporal_model": model["temporal_model"],
                "fusion": model["fusion"],
            },
            "reason_codes": {
                "observed_signals": reasons[
                    "observed_signals"
                ],
                "risk_drivers": reasons[
                    "model_risk_drivers"
                ],
                "protective_drivers": reasons[
                    "model_protective_drivers"
                ],
            },
            "graph_evidence": {
                "case_id": graph.get("case_id"),
                "graph_feature_snapshot": graph[
                    "graph_feature_snapshot"
                ],
                "graph_explanation_signals": graph[
                    "graph_explanation_signals"
                ],
                "investigation_graph": graph[
                    "investigation_graph"
                ],
                "path_evidence": graph[
                    "path_evidence"
                ],
                "evidence_summary": graph[
                    "evidence_summary"
                ],
            },
            "temporal_evidence": {
                "tgn_component": temporal[
                    "tgn_component"
                ],
                "temporal_feature_snapshot": temporal[
                    "temporal_feature_snapshot"
                ],
                "temporal_observations": temporal[
                    "temporal_observations"
                ],
            },
            "explanation_boundaries": {
                "tree_shap_applies_to_graph_lightgbm_only": True,
                "tgn_explained_with_temporal_context_not_shap": True,
                "reason_codes_are_not_proof_of_wrongdoing": True,
                "policy_or_legal_conclusion_included": False,
                "ground_truth_label_exposed": False,
            },
            "governance": {
                "mode": "decision_support_only",
                "human_review_required": True,
                "certified_phase10_artifacts": "read_only",
                "autonomous_account_blocking": False,
                "autonomous_case_closure": False,
                "autonomous_regulatory_filing": False,
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--transaction-id",
        required=True,
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
    )

    args = parser.parse_args()

    result = Phase11ExplanationBundleService().build(
        transaction_id=args.transaction_id,
        top_k=args.top_k,
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
