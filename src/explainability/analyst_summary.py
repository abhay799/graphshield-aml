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

from explainability.explanation_bundle import (
    Phase11ExplanationBundleService,
)


class Phase11AnalystSummaryService:
    """
    Deterministic investigator-readable summary.

    No LLM is used. Every statement is derived from the canonical
    Phase 11 explanation bundle. The summary is decision support only.
    """

    def __init__(self) -> None:
        self.bundle = Phase11ExplanationBundleService()

    @staticmethod
    def _driver_line(
        item: dict[str, Any],
    ) -> str:
        return (
            f"{item['feature']}={item.get('feature_value')} "
            f"(TreeSHAP raw-margin contribution "
            f"{float(item['shap_value_raw_margin']):.6g})"
        )

    def build(
        self,
        transaction_id: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        explanation = self.bundle.build(
            transaction_id=transaction_id,
            top_k=max(top_k, 3),
        )

        scores = explanation["scores"]
        reasons = explanation["reason_codes"]
        graph = explanation["graph_evidence"]
        temporal = explanation["temporal_evidence"]

        risk_drivers = reasons[
            "risk_drivers"
        ][:top_k]

        protective_drivers = reasons[
            "protective_drivers"
        ][:top_k]

        observed = reasons[
            "observed_signals"
        ]

        observed_titles = [
            item["title"]
            for item in observed
        ]

        risk_driver_lines = [
            self._driver_line(item)
            for item in risk_drivers
        ]

        protective_driver_lines = [
            self._driver_line(item)
            for item in protective_drivers
        ]

        temporal_titles = [
            item["title"]
            for item in temporal[
                "temporal_observations"
            ]
        ]

        fusion_score = scores.get(
            "fusion_score_calibrated"
        )

        graph_score = scores.get(
            "graph_score_calibrated"
        )

        summary_parts = [
            (
                "GraphShield generated an explainable AML "
                "decision-support assessment for transaction "
                f"{transaction_id}."
            )
        ]

        if fusion_score is not None:
            summary_parts.append(
                "Frozen Phase 10 fusion calibrated score: "
                f"{float(fusion_score):.8f}."
            )
        elif graph_score is not None:
            summary_parts.append(
                "Frozen graph-model calibrated score: "
                f"{float(graph_score):.8f}."
            )

        if observed_titles:
            summary_parts.append(
                "Observed deterministic signals: "
                + "; ".join(observed_titles)
                + "."
            )

        if risk_driver_lines:
            summary_parts.append(
                "Top model risk-raising drivers: "
                + "; ".join(risk_driver_lines)
                + "."
            )

        if protective_driver_lines:
            summary_parts.append(
                "Top model risk-lowering drivers: "
                + "; ".join(protective_driver_lines)
                + "."
            )

        if temporal_titles:
            summary_parts.append(
                "Temporal context: "
                + "; ".join(temporal_titles)
                + "."
            )

        if graph["investigation_graph"].get(
            "available"
        ):
            summary_parts.append(
                "A materialized investigation graph is "
                "available for this case."
            )
        else:
            summary_parts.append(
                "No materialized investigation graph is "
                "attached to this transaction in the "
                "current case store."
            )

        summary_parts.append(
            "These indicators are model/evidence signals only; "
            "they are not proof of money laundering. Human "
            "analyst review is required."
        )

        return {
            "schema_version":
                "phase11_analyst_summary_v1",

            "transaction_id":
                transaction_id,

            "event_ts":
                explanation.get(
                    "event_ts"
                ),

            "summary":
                " ".join(
                    summary_parts
                ),

            "observed_signal_titles":
                observed_titles,

            "top_risk_drivers":
                risk_drivers,

            "top_protective_drivers":
                protective_drivers,

            "temporal_observation_titles":
                temporal_titles,

            "case_id":
                graph.get(
                    "case_id"
                ),

            "scores":
                scores,

            "limitations": [
                (
                    "TreeSHAP attribution applies to the frozen "
                    "LightGBM graph model only."
                ),
                (
                    "The TGN component is represented by its "
                    "frozen score and temporal context, not SHAP."
                ),
                (
                    "Risk signals do not establish criminal or "
                    "regulatory conclusions."
                ),
            ],

            "governance": {
                "mode":
                    "decision_support_only",

                "human_review_required":
                    True,

                "certified_phase10_artifacts":
                    "read_only",

                "ground_truth_label_exposed":
                    False,

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

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
    )

    args = parser.parse_args()

    result = (
        Phase11AnalystSummaryService()
        .build(
            transaction_id=args.transaction_id,
            top_k=args.top_k,
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
