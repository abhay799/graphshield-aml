from __future__ import annotations

import json
import time
from typing import Any, Callable

from explainability.case_explanation import (
    Phase11CaseExplanationService,
)
from retrieval.policy_retriever import PolicyRetriever
from retrieval.retriever import EvidenceRetriever

from investigation.phase12_contracts import (
    ToolCallRequest,
    ToolCallResult,
)


class Phase12InvestigationTools:
    """
    Typed, read-only tool registry for Phase 12.

    No arbitrary Python, shell, database-write, account-action,
    case-closure, or regulatory-filing tool is exposed.
    """

    ALLOWED_TOOLS = {
        "case_overview",
        "search_evidence",
        "path_evidence",
        "history_evidence",
        "policy_search",
        "phase11_explanation",
    }

    def __init__(
        self,
        enable_policy_reranker: bool = False,
    ) -> None:
        self.case_retriever = EvidenceRetriever()
        self.case_explainer = (
            Phase11CaseExplanationService()
        )
        self.enable_policy_reranker = (
            enable_policy_reranker
        )
        self._policy_retriever = None

        self._registry: dict[
            str,
            Callable[[ToolCallRequest], Any],
        ] = {
            "case_overview":
                self._case_overview,
            "search_evidence":
                self._search_evidence,
            "path_evidence":
                self._path_evidence,
            "history_evidence":
                self._history_evidence,
            "policy_search":
                self._policy_search,
            "phase11_explanation":
                self._phase11_explanation,
        }

    def _case_overview(
        self,
        request: ToolCallRequest,
    ) -> list[dict[str, Any]]:
        docs = []

        for source_type in (
            "focal_transaction",
            "rule_evidence",
            "graph_summary",
        ):
            docs.extend(
                self.case_retriever.source_type(
                    request.case_id,
                    source_type,
                )
            )

        return docs[: request.top_k]

    def _search_evidence(
        self,
        request: ToolCallRequest,
    ) -> list[dict[str, Any]]:
        if not request.query:
            raise ValueError(
                "search_evidence requires query."
            )

        return self.case_retriever.search(
            request.case_id,
            request.query,
            top_k=request.top_k,
        )

    def _path_evidence(
        self,
        request: ToolCallRequest,
    ) -> list[dict[str, Any]]:
        return self.case_retriever.source_type(
            request.case_id,
            "graph_path",
        )[: request.top_k]

    def _history_evidence(
        self,
        request: ToolCallRequest,
    ) -> list[dict[str, Any]]:
        return self.case_retriever.source_type(
            request.case_id,
            "historical_transactions",
        )[: request.top_k]

    def _policy_search(
        self,
        request: ToolCallRequest,
    ) -> list[dict[str, Any]]:
        if not request.query:
            raise ValueError(
                "policy_search requires query."
            )

        if self._policy_retriever is None:
            self._policy_retriever = (
                PolicyRetriever(
                    enable_reranker=
                        self.enable_policy_reranker
                )
            )

        return self._policy_retriever.search(
            request.query,
            top_k=request.top_k,
        )

    def _phase11_explanation(
        self,
        request: ToolCallRequest,
    ) -> dict[str, Any]:
        return (
            self.case_explainer
            .explain_case(
                request.case_id,
                top_k=request.top_k,
            )
        )

    @staticmethod
    def _evidence_ids(
        payload: Any,
    ) -> list[str]:
        ids: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                evidence_id = value.get(
                    "evidence_id"
                )

                if evidence_id:
                    ids.append(
                        str(evidence_id)
                    )

                chunk_id = value.get(
                    "chunk_id"
                )

                if chunk_id:
                    ids.append(
                        f"POLICY:{chunk_id}"
                    )

                for child in value.values():
                    visit(child)

            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(payload)

        return sorted(set(ids))

    def execute(
        self,
        request: ToolCallRequest,
    ) -> ToolCallResult:
        if request.tool_name not in (
            self.ALLOWED_TOOLS
        ):
            raise RuntimeError(
                "Attempted execution of "
                "non-allowlisted Phase 12 tool."
            )

        handler = self._registry[
            request.tool_name
        ]

        started = time.perf_counter()

        try:
            payload = handler(
                request
            )

            latency_ms = (
                time.perf_counter()
                - started
            ) * 1000.0

            return ToolCallResult(
                tool_name=request.tool_name,
                success=True,
                case_id=request.case_id,
                evidence_ids=
                    self._evidence_ids(
                        payload
                    ),
                payload=payload,
                error=None,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = (
                time.perf_counter()
                - started
            ) * 1000.0

            return ToolCallResult(
                tool_name=request.tool_name,
                success=False,
                case_id=request.case_id,
                evidence_ids=[],
                payload=None,
                error=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
                latency_ms=latency_ms,
            )
