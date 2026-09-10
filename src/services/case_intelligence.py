from __future__ import annotations

from typing import Any

from services.analyst_state import (
    AnalystStateService,
)

from services.case_graph_service import (
    CaseGraphService,
)

from services.graphshield_service import (
    GraphShieldService,
)


class CaseIntelligenceService:
    """
    Deterministic analyst dossier builder.

    Reads Phase 1-6 intelligence artifacts and Phase 7
    operational analyst state.

    No autonomous regulatory/action decisions.
    No writes to certified Phase 1-6 artifacts.
    """

    def __init__(
        self,
        enable_policy_reranker: bool = False,
    ) -> None:

        self.graphshield = (
            GraphShieldService(
                enable_policy_reranker=
                    enable_policy_reranker
            )
        )

        self.case_graph = (
            CaseGraphService()
        )

        self.analyst_state = (
            AnalystStateService()
        )


    def build(
        self,
        case_id: str,
        question: str | None = None,
        evidence_top_k: int = 5,
        include_policy: bool = True,
        policy_top_k: int = 5,
        jurisdiction: str | None = None,
    ) -> dict[str, Any]:

        # ----------------------------------------------------
        # Validate authoritative queue membership.
        # ----------------------------------------------------

        case = (
            self.graphshield
            .get_case(
                case_id
            )
        )


        # ----------------------------------------------------
        # Deterministic investigation evidence.
        # ----------------------------------------------------

        overview = (
            self.graphshield
            .case_overview(
                case_id
            )
        )

        paths = (
            self.graphshield
            .path_evidence(
                case_id
            )
        )

        history = (
            self.graphshield
            .history_evidence(
                case_id
            )
        )


        # ----------------------------------------------------
        # Graph summary.
        #
        # Only the top-374 investigations are eagerly
        # materialized. Remaining queue cases are valid but
        # may not yet have graph evidence on disk.
        # ----------------------------------------------------

        try:

            graph = (
                self.case_graph
                .get_graph(
                    case_id=
                        case_id,

                    max_edges=
                        200,
                )
            )

            graph_summary = {
                "materialized":
                    True,

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

                "focal_transaction_id":
                    graph.get(
                        "focal_transaction_id"
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

            graph_summary = {
                "materialized":
                    False,

                "reason":
                    (
                        "Case is in the authoritative "
                        "7,617-case queue but is outside "
                        "the top-374 eagerly materialized "
                        "investigation set."
                    ),
            }


        # ----------------------------------------------------
        # Analyst operational state.
        # ----------------------------------------------------

        analyst_state = (
            self.analyst_state
            .get_case_state(
                case_id
            )
        )

        audit_events = (
            self.analyst_state
            .case_audit_history(
                case_id=
                    case_id,

                limit=
                    100,
            )
        )


        # ----------------------------------------------------
        # Optional question-grounded retrieval.
        # ----------------------------------------------------

        clean_question = (
            question.strip()
            if question
            else ""
        )

        evidence = []

        policy = []


        if clean_question:

            evidence = (
                self.graphshield
                .search_evidence(
                    case_id=
                        case_id,

                    query=
                        clean_question,

                    top_k=
                        evidence_top_k,
                )
            )


            if include_policy:

                policy = (
                    self.graphshield
                    .search_policy(
                        query=
                            clean_question,

                        top_k=
                            policy_top_k,

                        jurisdiction=
                            jurisdiction,
                    )
                )


        return {
            "case_id":
                case_id,

            "case":
                case,

            "graph":
                graph_summary,

            "investigation": {
                "overview":
                    overview,

                "paths":
                    paths,

                "history":
                    history,
            },

            "question":
                clean_question
                or None,

            "retrieval": {
                "case_evidence":
                    evidence,

                "policy_grounding":
                    policy,

                "policy_requested":
                    bool(
                        clean_question
                        and include_policy
                    ),
            },

            "analyst": {
                "state":
                    analyst_state,

                "audit_event_count":
                    len(
                        audit_events
                    ),

                "recent_audit_events":
                    audit_events[:10],
            },

            "governance": {
                "mode":
                    "decision_support_only",

                "human_review_required":
                    True,

                "autonomous_account_blocking":
                    False,

                "autonomous_case_closure":
                    False,

                "autonomous_regulatory_filing":
                    False,

                "phase_1_6_artifacts":
                    "read_only",
            },
        }
