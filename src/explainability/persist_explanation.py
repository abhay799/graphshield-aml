from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from explainability.analyst_summary import (
    Phase11AnalystSummaryService,
)
from explainability.explanation_bundle import (
    Phase11ExplanationBundleService,
)
from explainability.explanation_evidence import (
    Phase11ExplanationEvidenceService,
)


OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "explanations"
    / "phase11"
)


class Phase11ExplanationPersistenceService:
    """
    On-demand persistence of derived Phase 11 explanation artifacts.

    Writes only under data/processed/explanations/phase11.
    Certified Phase 10 artifacts are never modified.
    """

    def __init__(self) -> None:
        self.bundle = (
            Phase11ExplanationBundleService()
        )
        self.summary = (
            Phase11AnalystSummaryService()
        )
        self.evidence = (
            Phase11ExplanationEvidenceService()
        )

    @staticmethod
    def _canonical_bytes(
        payload: dict[str, Any],
    ) -> bytes:
        return json.dumps(
            payload,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _safe_name(
        transaction_id: str,
    ) -> str:
        allowed = []

        for char in str(
            transaction_id
        ):
            if (
                char.isalnum()
                or char in {"-", "_", "."}
            ):
                allowed.append(
                    char
                )
            else:
                allowed.append(
                    "_"
                )

        return "".join(
            allowed
        )

    def build_payload(
        self,
        transaction_id: str,
        top_k: int = 8,
    ) -> dict[str, Any]:
        explanation = self.bundle.build(
            transaction_id=transaction_id,
            top_k=top_k,
        )

        analyst_summary = self.summary.build(
            transaction_id=transaction_id,
            top_k=min(
                top_k,
                5,
            ),
        )

        evidence_documents = (
            self.evidence.build_documents(
                transaction_id=
                    transaction_id,
                top_k=top_k,
            )
        )

        return {
            "schema_version":
                "phase11_persisted_explanation_v1",

            "transaction_id":
                transaction_id,

            "explanation":
                explanation,

            "analyst_summary":
                analyst_summary,

            "evidence_documents":
                evidence_documents,

            "provenance": {
                "phase": 11,
                "certified_phase10_artifacts":
                    "read_only",
                "generated_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
            },

            "governance": {
                "mode":
                    "decision_support_only",

                "human_review_required":
                    True,

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

    def persist(
        self,
        transaction_id: str,
        top_k: int = 8,
    ) -> dict[str, Any]:
        payload = self.build_payload(
            transaction_id=transaction_id,
            top_k=top_k,
        )

        payload_for_hash = dict(
            payload
        )

        payload_for_hash[
            "provenance"
        ] = dict(
            payload[
                "provenance"
            ]
        )

        payload_for_hash[
            "provenance"
        ].pop(
            "generated_at",
            None,
        )

        digest = hashlib.sha256(
            self._canonical_bytes(
                payload_for_hash
            )
        ).hexdigest()

        payload[
            "provenance"
        ][
            "content_sha256"
        ] = digest

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = (
            OUTPUT_DIR
            / (
                self._safe_name(
                    transaction_id
                )
                + ".json"
            )
        )

        path.write_text(
            json.dumps(
                payload,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        return {
            "status": "saved",
            "transaction_id":
                transaction_id,
            "path":
                str(path),
            "content_sha256":
                digest,
            "evidence_document_count":
                len(
                    payload[
                        "evidence_documents"
                    ]
                ),
            "certified_phase10_artifacts":
                "read_only",
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

    result = (
        Phase11ExplanationPersistenceService()
        .persist(
            transaction_id=args.transaction_id,
            top_k=args.top_k,
        )
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
