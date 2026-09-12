from __future__ import annotations

from typing import Any

from explainability.case_explanation import (
    Phase11CaseExplanationService,
)
from services.case_intelligence import (
    CaseIntelligenceService,
)


class Phase11CaseIntelligenceService:
    """
    Explainable analyst dossier.

    Composes the existing deterministic case-intelligence service with
    the canonical Phase 11 explanation service without mutating either
    certified Phase 10 artifacts or earlier investigation artifacts.
    """

    def __init__(
        self,
        enable_policy_reranker: bool = False,
    ) -> None:
        self.base = CaseIntelligenceService(
            enable_policy_reranker=
                enable_policy_reranker
        )
        self.explanations = (
            Phase11CaseExplanationService()
        )

    def build(
        self,
        case_id: str,
        question: str | None = None,
        evidence_top_k: int = 5,
        include_policy: bool = True,
        policy_top_k: int = 5,
        jurisdiction: str | None = None,
        explanation_top_k: int = 8,
    ) -> dict[str, Any]:
        dossier = self.base.build(
            case_id=case_id,
            question=question,
            evidence_top_k=evidence_top_k,
            include_policy=include_policy,
            policy_top_k=policy_top_k,
            jurisdiction=jurisdiction,
        )

        explanation = (
            self.explanations.explain_case(
                case_id=case_id,
                top_k=explanation_top_k,
            )
        )

        dossier["phase11_explanation"] = (
            explanation
        )

        governance = dossier.setdefault(
            "governance",
            {},
        )

        governance.update(
            {
                "mode": "decision_support_only",
                "human_review_required": True,
                "certified_phase10_artifacts":
                    "read_only",
                "phase11_explanations":
                    "read_only_derived_evidence",
                "autonomous_account_blocking":
                    False,
                "autonomous_case_closure":
                    False,
                "autonomous_regulatory_filing":
                    False,
            }
        )

        return dossier
