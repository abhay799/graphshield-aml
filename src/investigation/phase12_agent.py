from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from investigation.phase12_audit import (
    append_hash_chained_record,
)
from investigation.phase12_contracts import (
    InvestigationPlan,
    InvestigationResult,
    ToolCallRequest,
)
from investigation.phase12_contradiction import (
    build_contradiction_findings,
)
from investigation.phase12_grounding import (
    validate_claim_citations,
)
from investigation.phase12_tools import (
    Phase12InvestigationTools,
)
from retrieval.grounded_llm import (
    generate_grounded_answer,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

AUDIT_LOG = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase12"
    / "agent_audit_chain.jsonl"
)


POLICY_TERMS = {
    "policy",
    "regulation",
    "regulatory",
    "requirement",
    "requirements",
    "compliance",
    "fatf",
    "fincen",
    "rbi",
    "fiu",
    "kyc",
    "cdd",
    "edd",
    "sar",
    "str",
    "guideline",
    "obligation",
    "reporting",
}

GRAPH_TERMS = {
    "path",
    "cycle",
    "network",
    "graph",
    "relationship",
    "counterparty",
}

HISTORY_TERMS = {
    "history",
    "previous",
    "prior",
    "transaction",
    "activity",
    "velocity",
    "temporal",
}


def _utcnow() -> datetime:
    return datetime.now(
        timezone.utc
    )


def build_plan(
    case_id: str,
    question: str,
    max_tool_calls: int = 6,
) -> InvestigationPlan:
    q = question.lower()

    tools = [
        "case_overview",
        "search_evidence",
        "phase11_explanation",
    ]

    rationale = [
        "Retrieve deterministic case overview.",
        "Perform question-grounded case evidence search.",
        "Include the certified Phase 11 explanation.",
    ]

    include_policy = any(
        term in q
        for term in POLICY_TERMS
    )

    if include_policy:
        tools.append(
            "policy_search"
        )
        rationale.append(
            "Policy language detected."
        )

    if any(
        term in q
        for term in GRAPH_TERMS
    ):
        tools.append(
            "path_evidence"
        )
        rationale.append(
            "Graph/network language detected."
        )

    if any(
        term in q
        for term in HISTORY_TERMS
    ):
        tools.append(
            "history_evidence"
        )
        rationale.append(
            "Historical/temporal language detected."
        )

    tools = tools[
        :max_tool_calls
    ]

    return InvestigationPlan(
        case_id=case_id,
        question=question,
        planned_tools=tools,
        max_tool_calls=max_tool_calls,
        include_policy=include_policy,
        rationale=rationale,
    )


def _phase11_documents(
    payload: dict,
) -> list[dict]:
    explanation = payload.get(
        "explanation",
        {},
    )

    transaction_id = payload.get(
        "transaction_id",
        "unknown",
    )

    documents = []

    for section in (
        "model_explanation",
        "reason_codes",
        "graph_evidence",
        "temporal_evidence",
    ):
        content = explanation.get(
            section
        )

        if content is None:
            continue

        evidence_id = (
            "EVID_"
            + uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    "phase12://"
                    f"{transaction_id}/"
                    f"{section}"
                ),
            ).hex[:16].upper()
        )

        documents.append(
            {
                "evidence_id":
                    evidence_id,
                "source_type":
                    f"phase11_{section}",
                "source_ref":
                    (
                        "phase11://"
                        f"{transaction_id}/"
                        f"{section}"
                    ),
                "content":
                    json.dumps(
                        content,
                        default=str,
                        sort_keys=True,
                    ),
            }
        )

    return documents


def _tool_documents(
    result,
) -> list[dict]:
    if not result.success:
        return []

    if (
        result.tool_name
        == "phase11_explanation"
        and isinstance(
            result.payload,
            dict,
        )
    ):
        return _phase11_documents(
            result.payload
        )

    payload = result.payload

    if isinstance(
        payload,
        list,
    ):
        return [
            item
            for item in payload
            if isinstance(
                item,
                dict,
            )
            and (
                item.get(
                    "evidence_id"
                )
                or item.get(
                    "chunk_id"
                )
            )
        ]

    if isinstance(
        payload,
        dict,
    ) and (
        payload.get(
            "evidence_id"
        )
        or payload.get(
            "chunk_id"
        )
    ):
        return [payload]

    return []


def _document_id(
    document: dict,
) -> str:
    if document.get(
        "evidence_id"
    ):
        return str(
            document[
                "evidence_id"
            ]
        )

    return (
        "POLICY:"
        + str(
            document[
                "chunk_id"
            ]
        )
    )


def _deduplicate_documents(
    documents: list[dict],
) -> list[dict]:
    seen = set()
    result = []

    for document in documents:
        key = _document_id(
            document
        )

        if key in seen:
            continue

        seen.add(
            key
        )
        result.append(
            document
        )

    return result


class Phase12InvestigationAgent:
    """
    Bounded and auditable investigation orchestrator.

    Tool planning/execution is deterministic and allowlisted.
    The LLM cannot directly call tools.
    Generated answers are withheld unless strict claim-level
    citation validation passes.
    """

    def __init__(
        self,
        enable_policy_reranker: bool = False,
        max_tool_calls: int = 6,
        max_evidence_documents: int = 24,
    ) -> None:
        if not 1 <= max_tool_calls <= 8:
            raise ValueError(
                "max_tool_calls must be 1..8."
            )

        if not 1 <= max_evidence_documents <= 40:
            raise ValueError(
                "max_evidence_documents must be 1..40."
            )

        self.tools = (
            Phase12InvestigationTools(
                enable_policy_reranker=
                    enable_policy_reranker
            )
        )

        self.max_tool_calls = (
            max_tool_calls
        )
        self.max_evidence_documents = (
            max_evidence_documents
        )

    def run(
        self,
        case_id: str,
        question: str,
    ) -> InvestigationResult:
        clean_question = (
            question.strip()
        )

        if not clean_question:
            raise ValueError(
                "Question must not be empty."
            )

        run_id = str(
            uuid.uuid4()
        )

        result = InvestigationResult(
            run_id=run_id,
            case_id=case_id,
            question=clean_question,
            status="running",
            started_at=_utcnow(),
            plan=build_plan(
                case_id=case_id,
                question=clean_question,
                max_tool_calls=
                    self.max_tool_calls,
            ),
        )

        documents: list[dict] = []

        try:
            for tool_name in (
                result.plan.planned_tools
            ):
                request = ToolCallRequest(
                    tool_name=tool_name,
                    case_id=case_id,
                    query=(
                        clean_question
                        if tool_name
                        in {
                            "search_evidence",
                            "policy_search",
                        }
                        else None
                    ),
                    top_k=5,
                )

                tool_result = (
                    self.tools.execute(
                        request
                    )
                )

                result.tool_results.append(
                    tool_result
                )

                documents.extend(
                    _tool_documents(
                        tool_result
                    )
                )

            documents = (
                _deduplicate_documents(
                    documents
                )
                [
                    :self.max_evidence_documents
                ]
            )

            result.retrieved_evidence_ids = [
                _document_id(
                    document
                )
                for document in documents
            ]

            result.contradictions = (
                build_contradiction_findings(
                    result.tool_results
                )
            )

            grounded = (
                generate_grounded_answer(
                    clean_question,
                    documents,
                )
            )

            candidate_answer = str(
                grounded[
                    "answer"
                ]
            )

            strict_validation = (
                validate_claim_citations(
                    candidate_answer,
                    set(
                        result.retrieved_evidence_ids
                    ),
                )
            )

            result.grounding_validation = (
                strict_validation
            )

            result.cited_ids = list(
                grounded.get(
                    "cited_ids",
                    [],
                )
            )

            result.citation_validation_passed = (
                bool(
                    grounded.get(
                        "validation_passed"
                    )
                )
                and bool(
                    strict_validation[
                        "passed"
                    ]
                )
            )

            if (
                result.citation_validation_passed
            ):
                result.answer = (
                    candidate_answer
                )
                result.answer_withheld = (
                    False
                )
            else:
                result.answer = (
                    "Grounded answer withheld because "
                    "claim-level citation validation "
                    "did not pass. Human analyst review "
                    "is required."
                )
                result.answer_withheld = (
                    True
                )

            result.status = "completed"
            result.completed_at = (
                _utcnow()
            )

        except Exception as exc:
            result.status = "failed"
            result.failure_reason = (
                f"{type(exc).__name__}: {exc}"
            )
            result.completed_at = (
                _utcnow()
            )
            self._audit(
                result
            )
            raise

        self._audit(
            result
        )

        return result

    @staticmethod
    def _audit(
        result: InvestigationResult,
    ) -> None:
        append_hash_chained_record(
            AUDIT_LOG,
            result.model_dump(
                mode="json"
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--case-id",
        required=True,
    )

    parser.add_argument(
        "--question",
        required=True,
    )

    args = parser.parse_args()

    result = (
        Phase12InvestigationAgent()
        .run(
            case_id=args.case_id,
            question=args.question,
        )
    )

    print(
        json.dumps(
            result.model_dump(
                mode="json"
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
