from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from investigation.investigation_agent import (
    InvestigationTools,
)

from retrieval.policy_retriever import (
    PolicyRetriever,
)

from retrieval.retriever import (
    EvidenceRetriever,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]


CASE_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)


class GraphShieldService:
    """
    Read-only integration layer for GraphShield AML.

    Phase 1-6 artifacts are treated as immutable inputs.
    This service exposes analyst-facing operations without
    rewriting certified data or model artifacts.
    """

    def __init__(
        self,
        enable_policy_reranker: bool = True,
    ) -> None:

        if not CASE_QUEUE_PATH.exists():
            raise FileNotFoundError(
                f"Case queue missing: {CASE_QUEUE_PATH}"
            )

        self._queue = (
            pl.read_parquet(
                CASE_QUEUE_PATH
            )
            .sort(
                "risk_rank"
            )
        )

        self._evidence_retriever = (
            EvidenceRetriever()
        )

        self._policy_retriever = (
            PolicyRetriever(
                enable_reranker=
                    enable_policy_reranker
            )
        )

        self._investigation_tools = (
            InvestigationTools()
        )


    @staticmethod
    def _normalise(
        value: Any,
    ) -> Any:
        """
        Convert Polars / object-style values into JSON-friendly
        Python structures while preserving the original content.
        """

        if value is None:
            return None

        if isinstance(
            value,
            pl.DataFrame,
        ):
            return value.to_dicts()

        if isinstance(
            value,
            pl.Series,
        ):
            return value.to_list()

        if isinstance(
            value,
            dict,
        ):
            return {
                str(key):
                    GraphShieldService._normalise(
                        item
                    )
                for key, item
                in value.items()
            }

        if isinstance(
            value,
            (list, tuple),
        ):
            return [
                GraphShieldService._normalise(
                    item
                )
                for item in value
            ]

        if hasattr(
            value,
            "to_dict",
        ):
            try:
                return value.to_dict()
            except Exception:
                pass

        if hasattr(
            value,
            "__dict__",
        ):
            try:
                return {
                    str(key):
                        GraphShieldService._normalise(
                            item
                        )
                    for key, item
                    in vars(value).items()
                    if not key.startswith("_")
                }
            except Exception:
                pass

        return value


    def health(
        self,
    ) -> dict[str, Any]:

        return {
            "status":
                "ok",

            "service":
                "GraphShield AML",

            "mode":
                "read_only",

            "case_queue_rows":
                self._queue.height,

            "champion":
                "lightgbm_graph",

            "phase_1_6_artifacts":
                "frozen",
        }


    def list_cases(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:

        if limit < 1:
            raise ValueError(
                "limit must be at least 1"
            )

        if limit > 500:
            limit = 500

        if offset < 0:
            raise ValueError(
                "offset cannot be negative"
            )

        frame = (
            self._queue
            .slice(
                offset,
                limit,
            )
        )

        return frame.to_dicts()


    def get_case(
        self,
        case_id: str,
    ) -> dict[str, Any]:

        frame = (
            self._queue
            .filter(
                pl.col("case_id")
                == case_id
            )
        )

        if frame.height == 0:
            raise KeyError(
                f"Unknown case_id: {case_id}"
            )

        return frame.row(
            0,
            named=True,
        )


    def case_overview(
        self,
        case_id: str,
    ) -> Any:

        self.get_case(
            case_id
        )

        result = (
            self._investigation_tools
            .case_overview(
                case_id
            )
        )

        return self._normalise(
            result
        )


    def path_evidence(
        self,
        case_id: str,
    ) -> Any:

        self.get_case(
            case_id
        )

        result = (
            self._investigation_tools
            .path_evidence(
                case_id
            )
        )

        return self._normalise(
            result
        )


    def history_evidence(
        self,
        case_id: str,
    ) -> Any:

        self.get_case(
            case_id
        )

        result = (
            self._investigation_tools
            .history_evidence(
                case_id
            )
        )

        return self._normalise(
            result
        )


    def search_evidence(
        self,
        case_id: str,
        query: str,
        top_k: int = 5,
    ) -> Any:

        self.get_case(
            case_id
        )

        if not query.strip():
            raise ValueError(
                "Evidence query cannot be empty"
            )

        if top_k < 1:
            raise ValueError(
                "top_k must be at least 1"
            )

        result = (
            self._evidence_retriever
            .search(
                case_id,
                query,
                top_k,
            )
        )

        return self._normalise(
            result
        )


    def evidence_by_type(
        self,
        case_id: str,
        source_type: str,
    ) -> Any:

        self.get_case(
            case_id
        )

        result = (
            self._evidence_retriever
            .source_type(
                case_id,
                source_type,
            )
        )

        return self._normalise(
            result
        )


    def search_policy(
        self,
        query: str,
        top_k: int = 5,
        jurisdiction: str | None = None,
    ) -> Any:

        if not query.strip():
            raise ValueError(
                "Policy query cannot be empty"
            )

        if top_k < 1:
            raise ValueError(
                "top_k must be at least 1"
            )

        result = (
            self._policy_retriever
            .search(
                query,
                top_k,
                jurisdiction,
            )
        )

        return self._normalise(
            result
        )


    def investigation_snapshot(
        self,
        case_id: str,
    ) -> dict[str, Any]:
        """
        Build a deterministic analyst snapshot.

        No LLM call is required.
        """

        return {
            "case":
                self.get_case(
                    case_id
                ),

            "overview":
                self.case_overview(
                    case_id
                ),

            "paths":
                self.path_evidence(
                    case_id
                ),

            "history":
                self.history_evidence(
                    case_id
                ),
        }
