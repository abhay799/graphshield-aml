from __future__ import annotations

import argparse
import hashlib
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


SCHEMA_VERSION = "phase11_explanation_evidence_v1"


def _evidence_id(
    transaction_id: str,
    source_type: str,
) -> str:
    raw = (
        f"{SCHEMA_VERSION}|"
        f"{transaction_id}|"
        f"{source_type}"
    ).encode("utf-8")

    digest = hashlib.sha256(
        raw
    ).hexdigest()[:16].upper()

    return f"EVID_{digest}"


def _json_content(
    payload: dict[str, Any],
) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


class Phase11ExplanationEvidenceService:
    """
    Converts the canonical Phase 11 explanation bundle into deterministic,
    citation-ready evidence documents for later investigation/RAG use.

    No LLM generation is used here. Evidence IDs are stable hashes.
    """

    def __init__(self) -> None:
        self.bundle = Phase11ExplanationBundleService()

    def build_documents(
        self,
        transaction_id: str,
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        explanation = self.bundle.build(
            transaction_id=transaction_id,
            top_k=top_k,
        )

        sections = {
            "phase11_model_explanation": {
                "scores": explanation["scores"],
                "model_explanation": explanation[
                    "model_explanation"
                ],
            },
            "phase11_reason_codes": explanation[
                "reason_codes"
            ],
            "phase11_graph_evidence": explanation[
                "graph_evidence"
            ],
            "phase11_temporal_evidence": explanation[
                "temporal_evidence"
            ],
        }

        documents = []

        for source_type, payload in sections.items():
            evidence_id = _evidence_id(
                transaction_id,
                source_type,
            )

            documents.append(
                {
                    "evidence_id": evidence_id,
                    "source_type": source_type,
                    "source_ref": (
                        "phase11://transaction/"
                        f"{transaction_id}/"
                        f"{source_type}"
                    ),
                    "transaction_id": str(
                        transaction_id
                    ),
                    "schema_version": SCHEMA_VERSION,
                    "content": _json_content(
                        payload
                    ),
                    "provenance": {
                        "phase": 11,
                        "phase10_final_candidate":
                            explanation.get(
                                "phase10_final_candidate"
                            ),
                        "certified_phase10_artifacts":
                            "read_only",
                        "generated_by":
                            "deterministic_phase11_service",
                    },
                    "governance": {
                        "mode": "decision_support_only",
                        "human_review_required": True,
                        "ground_truth_label_exposed": False,
                        "autonomous_account_blocking": False,
                        "autonomous_case_closure": False,
                        "autonomous_regulatory_filing": False,
                    },
                }
            )

        return documents


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

    result = (
        Phase11ExplanationEvidenceService()
        .build_documents(
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
