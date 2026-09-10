from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

import argparse
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.append(
    str(
        PROJECT_ROOT
        / "src"
    )
)


from retrieval.retriever import (
    EvidenceRetriever,
)

from retrieval.policy_retriever import (
    PolicyRetriever,
)

from retrieval.grounded_llm import (
    generate_grounded_answer,
)


LOG_PATH = (
    PROJECT_ROOT
    / "reports"
    / "investigation"
    / "agent_audit_log.jsonl"
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
    "customer due diligence",
    "enhanced due diligence",
    "risk-based",
    "risk based",
    "sar",
    "str",
    "guideline",
    "guidelines",
    "obligation",
    "obligations",
    "reporting requirement",
    "monitoring requirement",
}


class InvestigationTools:

    ALLOWED_TOOLS = {
        "case_overview",
        "search_evidence",
        "path_evidence",
        "history_evidence",
        "policy_search",
    }

    def __init__(self):

        self.retriever = (
            EvidenceRetriever()
        )

        self._policy_retriever = None

    def case_overview(
        self,
        case_id,
    ):

        docs = []

        for source_type in [
            "focal_transaction",
            "rule_evidence",
            "graph_summary",
        ]:

            docs.extend(
                self.retriever.source_type(
                    case_id,
                    source_type,
                )
            )

        return docs

    def search_evidence(
        self,
        case_id,
        query,
    ):

        return self.retriever.search(
            case_id,
            query,
            top_k=6,
        )

    def path_evidence(
        self,
        case_id,
    ):

        return (
            self.retriever
            .source_type(
                case_id,
                "graph_path",
            )
        )

    def history_evidence(
        self,
        case_id,
    ):

        return (
            self.retriever
            .source_type(
                case_id,
                "historical_transactions",
            )
        )[:8]

    def policy_search(
        self,
        query,
    ):

        if self._policy_retriever is None:

            self._policy_retriever = (
                PolicyRetriever(
                    enable_reranker=True
                )
            )

        return (
            self._policy_retriever
            .search(
                query,
                top_k=5,
            )
        )


def question_needs_policy(
    question,
):

    question_lower = (
        question.lower()
    )

    return any(
        term in question_lower
        for term in POLICY_TERMS
    )


def select_tools(
    question,
):

    question_lower = (
        question.lower()
    )

    tools = [
        "case_overview",
        "search_evidence",
    ]

    if question_needs_policy(
        question
    ):

        tools.append(
            "policy_search"
        )

    if any(
        word in question_lower
        for word in [
            "path",
            "cycle",
            "network",
            "graph",
            "relationship",
        ]
    ):

        tools.append(
            "path_evidence"
        )

    if any(
        word in question_lower
        for word in [
            "history",
            "previous",
            "prior",
            "transaction",
            "activity",
        ]
    ):

        tools.append(
            "history_evidence"
        )

    # Hard tool-call limit.
    return tools[:5]


def document_key(
    document,
):

    evidence_id = document.get(
        "evidence_id"
    )

    if evidence_id:

        return evidence_id

    chunk_id = document.get(
        "chunk_id"
    )

    if chunk_id:

        return (
            f"POLICY:{chunk_id}"
        )

    raise RuntimeError(
        "Retrieved document has neither "
        "evidence_id nor policy chunk_id."
    )


def deduplicate(
    documents,
):

    seen = set()
    result = []

    for document in documents:

        key = document_key(
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


def main():

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

    tools = (
        InvestigationTools()
    )

    selected = select_tools(
        args.question
    )

    print(
        "\nAllowed tool calls:"
    )

    print(selected)

    evidence = []

    for tool_name in selected:

        if tool_name not in (
            tools.ALLOWED_TOOLS
        ):

            raise RuntimeError(
                "Attempted execution of "
                "non-allowlisted tool."
            )

        if tool_name == (
            "case_overview"
        ):

            result = (
                tools.case_overview(
                    args.case_id
                )
            )

        elif tool_name == (
            "search_evidence"
        ):

            result = (
                tools.search_evidence(
                    args.case_id,
                    args.question,
                )
            )

        elif tool_name == (
            "policy_search"
        ):

            result = (
                tools.policy_search(
                    args.question
                )
            )

        elif tool_name == (
            "path_evidence"
        ):

            result = (
                tools.path_evidence(
                    args.case_id
                )
            )

        elif tool_name == (
            "history_evidence"
        ):

            result = (
                tools.history_evidence(
                    args.case_id
                )
            )

        else:

            result = []

        evidence.extend(
            result
        )

    evidence = deduplicate(
        evidence
    )

    # Bound prompt size while preserving
    # retrieved case + policy evidence.
    evidence = evidence[:20]

    case_evidence_ids = [
        document[
            "evidence_id"
        ]
        for document in evidence
        if document.get(
            "evidence_id"
        )
    ]

    policy_evidence_ids = [
        (
            f"POLICY:"
            f"{document['chunk_id']}"
        )
        for document in evidence
        if document.get(
            "chunk_id"
        )
    ]

    print(
        "\nRetrieved case evidence:",
        len(
            case_evidence_ids
        ),
    )

    print(
        "Retrieved policy evidence:",
        len(
            policy_evidence_ids
        ),
    )

    result = (
        generate_grounded_answer(
            args.question,
            evidence,
        )
    )

    print(
        "\n--- AGENT ANSWER ---"
    )

    print(
        result[
            "answer"
        ]
    )

    print(
        "\nCitation validation:",
        result[
            "validation_passed"
        ],
    )

    LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_record = {
        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "case_id":
            args.case_id,

        "question":
            args.question,

        "allowed_tools":
            sorted(
                tools.ALLOWED_TOOLS
            ),

        "executed_tools":
            selected,

        "case_evidence_ids":
            case_evidence_ids,

        "policy_evidence_ids":
            policy_evidence_ids,

        "retrieved_citation_ids":
            (
                case_evidence_ids
                +
                policy_evidence_ids
            ),

        "answer":
            result[
                "answer"
            ],

        "cited_ids":
            result[
                "cited_ids"
            ],

        "case_cited_ids":
            result.get(
                "case_cited_ids",
                [],
            ),

        "policy_cited_ids":
            result.get(
                "policy_cited_ids",
                [],
            ),

        "invalid_citations":
            result[
                "invalid_citations"
            ],

        "citation_validation":
            result[
                "validation_passed"
            ],

        "model":
            result[
                "model"
            ],
    }

    with open(
        LOG_PATH,
        "a",
        encoding="utf-8",
    ) as file:

        file.write(
            json.dumps(
                audit_record
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
