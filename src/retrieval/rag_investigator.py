from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

import argparse
import json
import sys
import uuid

import duckdb


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
    / "rag_interactions.jsonl"
)

DB_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_store.duckdb"
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
    "reporting",
    "monitoring requirement",
    "guideline",
    "guidelines",
    "obligation",
    "obligations",
}


def should_retrieve_policy(
    question: str,
) -> bool:

    question_lower = (
        question.lower()
    )

    return any(
        term in question_lower
        for term in POLICY_TERMS
    )


def policy_citation_id(
    item: dict,
) -> str:

    return (
        f"POLICY:"
        f"{item['chunk_id']}"
    )


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

    parser.add_argument(
        "--top-k",
        type=int,
        default=6,
    )

    parser.add_argument(
        "--policy-top-k",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--force-policy",
        action="store_true",
        help=(
            "Retrieve authoritative policy "
            "evidence even when the question "
            "does not contain policy keywords."
        ),
    )

    args = parser.parse_args()

    # ======================================================
    # Case evidence retrieval
    # ======================================================

    case_retriever = (
        EvidenceRetriever()
    )

    case_evidence = (
        case_retriever.search(
            args.case_id,
            args.question,
            top_k=args.top_k,
        )
    )

    print(
        "\n--- RETRIEVED CASE EVIDENCE ---"
    )

    for item in case_evidence:

        print(
            f"{item['evidence_id']} | "
            f"{item['source_type']} | "
            f"{item['retrieval_score']:.4f}"
        )

    # ======================================================
    # Authoritative policy retrieval
    # ======================================================

    retrieve_policy = (
        args.force_policy
        or should_retrieve_policy(
            args.question
        )
    )

    policy_evidence = []

    if retrieve_policy:

        policy_retriever = (
            PolicyRetriever(
                enable_reranker=True
            )
        )

        policy_evidence = (
            policy_retriever.search(
                args.question,
                top_k=args.policy_top_k,
            )
        )

        print(
            "\n--- RETRIEVED POLICY EVIDENCE ---"
        )

        for item in policy_evidence:

            print(
                f"{policy_citation_id(item)} | "
                f"{item['authority']} | "
                f"page {item['page_number']} | "
                f"rank={item['rank']}"
            )

            print(
                f"    {item['title']} | "
                f"{item['version']}"
            )

    else:

        print(
            "\n--- POLICY RETRIEVAL ---"
        )

        print(
            "Skipped: question did not "
            "request regulatory/policy context."
        )

    # ======================================================
    # Combined grounded evidence
    # ======================================================

    combined_evidence = (
        case_evidence
        +
        policy_evidence
    )

    result = (
        generate_grounded_answer(
            args.question,
            combined_evidence,
        )
    )

    print(
        "\n--- ANSWER ---"
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

    if result[
        "invalid_citations"
    ]:

        print(
            "INVALID CITATIONS:",
            result[
                "invalid_citations"
            ],
        )

    # ======================================================
    # Interaction log
    # ======================================================

    LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    retrieved_case_ids = [
        item[
            "evidence_id"
        ]
        for item in case_evidence
    ]

    retrieved_policy_ids = [
        policy_citation_id(
            item
        )
        for item in policy_evidence
    ]

    record = {
        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "case_id":
            args.case_id,

        "question":
            args.question,

        "policy_retrieval_used":
            retrieve_policy,

        "retrieved_evidence_ids":
            retrieved_case_ids,

        "retrieved_policy_ids":
            retrieved_policy_ids,

        "retrieved_citation_ids":
            (
                retrieved_case_ids
                +
                retrieved_policy_ids
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

        "validation_passed":
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
                record
            )
            + "\n"
        )

    # ======================================================
    # Audit log
    # ======================================================

    con = duckdb.connect(
        str(
            DB_PATH
        )
    )

    con.execute(
        """
        INSERT INTO audit_log
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            str(
                uuid.uuid4()
            ),

            args.case_id,

            datetime.now(
                timezone.utc
            ),

            "rag_assistant",

            "CASE_QUESTION",

            json.dumps(
                {
                    "question":
                        args.question,

                    "policy_retrieval_used":
                        retrieve_policy,

                    "retrieved_evidence_ids":
                        retrieved_case_ids,

                    "retrieved_policy_ids":
                        retrieved_policy_ids,

                    "citation_validation":
                        record[
                            "validation_passed"
                        ],
                }
            ),
        ],
    )

    con.close()


if __name__ == "__main__":
    main()
