from __future__ import annotations

from pathlib import Path

import json
import sys

import polars as pl


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


CASE_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)

INTERACTION_PATH = (
    PROJECT_ROOT
    / "reports"
    / "investigation"
    / "rag_interactions.jsonl"
)

JSON_OUTPUT = (
    PROJECT_ROOT
    / "reports"
    / "investigation"
    / "rag_evaluation.json"
)

MD_OUTPUT = (
    PROJECT_ROOT
    / "reports"
    / "phase6_investigation_rag_report.md"
)


MAX_CASES = 10
TOP_K = 5


CASE_BENCHMARKS = [
    (
        "What was the focal transaction amount, "
        "currency, sender and receiver?",
        "focal_transaction",
    ),
    (
        "Which deterministic AML rules "
        "triggered for this case?",
        "rule_evidence",
    ),
    (
        "How large is the point-in-time "
        "investigation subgraph?",
        "graph_summary",
    ),
    (
        "Is there an alternate or reverse "
        "historical network path?",
        "graph_path",
    ),
]


POLICY_BENCHMARKS = [
    {
        "question":
            (
                "According to the FATF Recommendations, "
                "what customer due diligence and ongoing "
                "monitoring requirements apply?"
            ),

        "expected_document":
            "fatf_recommendations_2026",
    },

    {
        "question":
            (
                "What does FATF banking-sector guidance "
                "say about applying a risk-based approach?"
            ),

        "expected_document":
            "fatf_rba_banking_2014",
    },

    {
        "question":
            (
                "What are FinCEN's national AML and CFT "
                "priorities?"
            ),

        "expected_document":
            "fincen_aml_cft_priorities_2021",
    },

    {
        "question":
            (
                "What does FinCEN's October 2025 SAR FAQ "
                "say about suspicious activity reporting?"
            ),

        "expected_document":
            "fincen_sar_faq_october_2025",
    },

    {
        "question":
            (
                "What AML and CFT guidance applies to "
                "reporting entities providing virtual "
                "digital asset services in India?"
            ),

        "expected_document":
            "fiu_ind_aml_cft_guidelines_2026",
    },

    {
        "question":
            (
                "What does RBI's KYC Master Direction say "
                "about customer due diligence and ongoing "
                "monitoring?"
            ),

        "expected_document":
            "rbi_kyc_master_direction",
    },
]


def evaluate_case_retrieval():

    retriever = (
        EvidenceRetriever()
    )

    cases = (
        pl.read_parquet(
            CASE_QUEUE_PATH
        )
        .sort(
            "risk_rank"
        )
        .head(
            MAX_CASES
        )
    )

    total_queries = 0
    hits = 0
    reciprocal_rank_sum = 0.0

    details = []

    for case_id in (
        cases[
            "case_id"
        ].to_list()
    ):

        for (
            question,
            expected_source,
        ) in CASE_BENCHMARKS:

            total_queries += 1

            results = (
                retriever.search(
                    case_id,
                    question,
                    top_k=TOP_K,
                )
            )

            found_rank = None

            for rank, result in enumerate(
                results,
                start=1,
            ):

                if (
                    result.get(
                        "source_type"
                    )
                    ==
                    expected_source
                ):

                    found_rank = rank
                    break

            if found_rank is not None:

                hits += 1

                reciprocal_rank_sum += (
                    1.0
                    /
                    found_rank
                )

            details.append(
                {
                    "case_id":
                        case_id,

                    "question":
                        question,

                    "expected_source":
                        expected_source,

                    "found_rank":
                        found_rank,
                }
            )

    hit_at_k = (
        hits
        /
        max(
            total_queries,
            1,
        )
    )

    mrr = (
        reciprocal_rank_sum
        /
        max(
            total_queries,
            1,
        )
    )

    return {
        "queries":
            total_queries,

        "hits":
            hits,

        "hit_at_5":
            hit_at_k,

        "mean_reciprocal_rank":
            mrr,

        "details":
            details,
    }


def evaluate_policy_retrieval():

    retriever = (
        PolicyRetriever(
            enable_reranker=True
        )
    )

    total_queries = 0
    hits = 0
    reciprocal_rank_sum = 0.0

    details = []

    for benchmark in (
        POLICY_BENCHMARKS
    ):

        question = (
            benchmark[
                "question"
            ]
        )

        expected_document = (
            benchmark[
                "expected_document"
            ]
        )

        total_queries += 1

        results = (
            retriever.search(
                question,
                top_k=TOP_K,
            )
        )

        found_rank = None

        returned_documents = []

        for rank, result in enumerate(
            results,
            start=1,
        ):

            document_id = (
                result.get(
                    "document_id"
                )
            )

            returned_documents.append(
                document_id
            )

            if (
                document_id
                ==
                expected_document
                and
                found_rank is None
            ):

                found_rank = rank

        if found_rank is not None:

            hits += 1

            reciprocal_rank_sum += (
                1.0
                /
                found_rank
            )

        details.append(
            {
                "question":
                    question,

                "expected_document":
                    expected_document,

                "found_rank":
                    found_rank,

                "returned_documents":
                    returned_documents,
            }
        )

    hit_at_k = (
        hits
        /
        max(
            total_queries,
            1,
        )
    )

    mrr = (
        reciprocal_rank_sum
        /
        max(
            total_queries,
            1,
        )
    )

    return {
        "queries":
            total_queries,

        "hits":
            hits,

        "hit_at_5":
            hit_at_k,

        "mean_reciprocal_rank":
            mrr,

        "details":
            details,
    }


def evaluate_citations():

    if not INTERACTION_PATH.exists():

        return {
            "available":
                False,

            "reason":
                (
                    "No RAG interaction log "
                    "exists yet."
                ),
        }

    interactions = []

    with INTERACTION_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:

        for line in file:

            line = line.strip()

            if not line:
                continue

            interactions.append(
                json.loads(
                    line
                )
            )

    if not interactions:

        return {
            "available":
                False,

            "reason":
                (
                    "RAG interaction log "
                    "contains zero records."
                ),
        }

    citation_total = 0
    valid_citations = 0

    answers_with_citations = 0
    accepted_answers = 0

    case_citations = 0
    policy_citations = 0

    for item in interactions:

        retrieved = set(
            item.get(
                "retrieved_citation_ids",
                [],
            )
        )

        if not retrieved:

            retrieved.update(
                item.get(
                    "retrieved_evidence_ids",
                    [],
                )
            )

            retrieved.update(
                item.get(
                    "retrieved_policy_ids",
                    [],
                )
            )

        cited = item.get(
            "cited_ids",
            [],
        )

        if cited:
            answers_with_citations += 1

        if item.get(
            "validation_passed",
            False,
        ):

            accepted_answers += 1

        for citation in cited:

            citation_total += 1

            if citation.startswith(
                "EVID_"
            ):

                case_citations += 1

            elif citation.startswith(
                "POLICY:"
            ):

                policy_citations += 1

            if citation in retrieved:

                valid_citations += 1

    citation_precision = (
        valid_citations
        /
        citation_total
        if citation_total
        else None
    )

    citation_coverage = (
        answers_with_citations
        /
        len(
            interactions
        )
    )

    accepted_rate = (
        accepted_answers
        /
        len(
            interactions
        )
    )

    return {
        "available":
            True,

        "interactions":
            len(
                interactions
            ),

        "citations":
            citation_total,

        "case_citations":
            case_citations,

        "policy_citations":
            policy_citations,

        "valid_citations":
            valid_citations,

        "citation_precision":
            citation_precision,

        "citation_coverage":
            citation_coverage,

        "accepted_answer_rate":
            accepted_rate,
    }


def format_metric(
    value,
):

    if value is None:
        return "N/A"

    return f"{value:.4f}"


def main():

    print("=" * 90)

    print(
        "GraphShield AML - "
        "Phase 6 Case + Policy RAG Evaluation"
    )

    print("=" * 90)

    JSON_OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "\n[1/3] Evaluating case retrieval..."
    )

    case_retrieval = (
        evaluate_case_retrieval()
    )

    print(
        "\n[2/3] Evaluating authoritative "
        "policy retrieval..."
    )

    policy_retrieval = (
        evaluate_policy_retrieval()
    )

    print(
        "\n[3/3] Evaluating citations..."
    )

    citations = (
        evaluate_citations()
    )

    report = {
        "case_retrieval":
            case_retrieval,

        "policy_retrieval":
            policy_retrieval,

        "citations":
            citations,
    }

    JSON_OUTPUT.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "Case Retrieval Hit@5:",
        case_retrieval[
            "hit_at_5"
        ],
    )

    print(
        "Case Retrieval MRR:",
        case_retrieval[
            "mean_reciprocal_rank"
        ],
    )

    print()
    print(
        "Policy Retrieval Hit@5:",
        policy_retrieval[
            "hit_at_5"
        ],
    )

    print(
        "Policy Retrieval MRR:",
        policy_retrieval[
            "mean_reciprocal_rank"
        ],
    )

    if citations[
        "available"
    ]:

        print()
        print(
            "Citation precision:",
            citations[
                "citation_precision"
            ],
        )

        print(
            "Citation coverage:",
            citations[
                "citation_coverage"
            ],
        )

        print(
            "Accepted answer rate:",
            citations[
                "accepted_answer_rate"
            ],
        )

    else:

        print()
        print(
            "Citation evaluation:",
            citations[
                "reason"
            ],
        )

    lines = [
        "# GraphShield AML - Phase 6 Investigation & RAG",
        "",
        "## Case Evidence Retrieval",
        "",
        (
            f"- Benchmark queries: "
            f"{case_retrieval['queries']}"
        ),
        (
            f"- Hit@5: "
            f"{case_retrieval['hit_at_5']:.4f}"
        ),
        (
            f"- Mean Reciprocal Rank: "
            f"{case_retrieval['mean_reciprocal_rank']:.4f}"
        ),
        "",
        "## Authoritative Policy Retrieval",
        "",
        (
            f"- Benchmark queries: "
            f"{policy_retrieval['queries']}"
        ),
        (
            f"- Hit@5: "
            f"{policy_retrieval['hit_at_5']:.4f}"
        ),
        (
            f"- Mean Reciprocal Rank: "
            f"{policy_retrieval['mean_reciprocal_rank']:.4f}"
        ),
        "",
        "## Citation Validation",
        "",
    ]

    if citations[
        "available"
    ]:

        lines.extend(
            [
                (
                    f"- Interactions evaluated: "
                    f"{citations['interactions']}"
                ),
                (
                    f"- Total citations: "
                    f"{citations['citations']}"
                ),
                (
                    f"- Case citations: "
                    f"{citations['case_citations']}"
                ),
                (
                    f"- Policy citations: "
                    f"{citations['policy_citations']}"
                ),
                (
                    f"- Citation precision: "
                    f"{format_metric(citations['citation_precision'])}"
                ),
                (
                    f"- Citation coverage: "
                    f"{format_metric(citations['citation_coverage'])}"
                ),
                (
                    f"- Accepted answer rate: "
                    f"{format_metric(citations['accepted_answer_rate'])}"
                ),
            ]
        )

    else:

        lines.append(
            (
                "- Citation metrics are not "
                "available until successful "
                "LLM-generated interactions exist."
            )
        )

    lines.extend(
        [
            "",
            "## Safety / Governance",
            "",
            (
                "- Ground-truth laundering labels are "
                "not exposed to the investigation assistant."
            ),
            (
                "- Case claims must be grounded in "
                "retrieved case evidence."
            ),
            (
                "- Policy claims must be grounded in "
                "retrieved authoritative policy chunks."
            ),
            (
                "- Unknown case or policy citation IDs "
                "fail citation validation."
            ),
            (
                "- Investigation tools are read-only "
                "and allowlisted."
            ),
            (
                "- Account blocking, case closure, "
                "SAR/STR filing, and regulatory reporting "
                "remain human decisions."
            ),
        ]
    )

    MD_OUTPUT.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    print()
    print(
        "Created:"
    )

    print(
        JSON_OUTPUT
    )

    print(
        MD_OUTPUT
    )


if __name__ == "__main__":
    main()
