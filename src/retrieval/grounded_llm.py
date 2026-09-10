import os
import re

from mistralai.client import Mistral


CASE_CITATION_PATTERN = re.compile(
    r"\[(EVID_[A-F0-9]{16})\]"
)

POLICY_CITATION_PATTERN = re.compile(
    r"\[(POLICY:[A-Za-z0-9_.:-]+)\]"
)


SYSTEM_PROMPT = """
You are the GraphShield AML investigation assistant.

Rules:

1. Use ONLY the supplied retrieved evidence.

2. Distinguish clearly between:
   - CASE EVIDENCE: facts about the investigated transaction/case.
   - POLICY EVIDENCE: authoritative regulatory or policy material.

3. Never use outside knowledge to invent case facts, regulatory
   obligations, thresholds, dates, or requirements.

4. Never state that a person or entity definitely committed
   money laundering.

5. Describe suspicious indicators as investigation evidence only.

6. Every factual statement about the case must cite at least one
   CASE evidence citation such as:
   [EVID_AB12CD34EF56AB78]

7. Every factual statement about regulatory/policy requirements
   must cite at least one POLICY citation such as:
   [POLICY:fatf_recommendations_2026_p0042_c002]

8. Use only citation IDs present in the supplied context.

9. If evidence is insufficient, contradictory, or does not support
   the requested conclusion, explicitly say so.

10. Do not claim that retrieved policy text constitutes legal advice
    or a definitive compliance determination.

11. Do not recommend autonomous account blocking, account closure,
    case closure, SAR/STR filing, or regulatory reporting.

12. Final investigation and compliance decisions require human
    analyst review.
"""


def citation_id_for_document(
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

    raise ValueError(
        "Retrieved document has neither "
        "evidence_id nor chunk_id."
    )


def build_case_block(
    document,
    citation_id,
):

    return (
        f"[{citation_id}]\n"
        f"Evidence kind: CASE\n"
        f"Source type: "
        f"{document.get('source_type', 'unknown')}\n"
        f"Source reference: "
        f"{document.get('source_ref', '')}\n"
        f"Content:\n"
        f"{document.get('content', '')}"
    )


def build_policy_block(
    document,
    citation_id,
):

    return (
        f"[{citation_id}]\n"
        f"Evidence kind: POLICY\n"
        f"Authority: "
        f"{document.get('authority', '')}\n"
        f"Title: "
        f"{document.get('title', '')}\n"
        f"Jurisdiction: "
        f"{document.get('jurisdiction', '')}\n"
        f"Version: "
        f"{document.get('version', '')}\n"
        f"Page: "
        f"{document.get('page_number', '')}\n"
        f"Chunk ID: "
        f"{document.get('chunk_id', '')}\n"
        f"Source URL: "
        f"{document.get('source_url', '')}\n"
        f"Content:\n"
        f"{document.get('content', '')}"
    )


def build_context(
    documents,
):

    blocks = []

    for document in documents:

        citation_id = (
            citation_id_for_document(
                document
            )
        )

        if document.get(
            "evidence_id"
        ):

            block = build_case_block(
                document,
                citation_id,
            )

        else:

            block = build_policy_block(
                document,
                citation_id,
            )

        blocks.append(
            block
        )

    return "\n\n".join(
        blocks
    )


def extract_citations(
    answer,
):

    case_ids = (
        CASE_CITATION_PATTERN.findall(
            answer
        )
    )

    policy_ids = (
        POLICY_CITATION_PATTERN.findall(
            answer
        )
    )

    return sorted(
        set(
            case_ids
            +
            policy_ids
        )
    )


def generate_grounded_answer(
    question,
    documents,
):

    if not documents:

        return {
            "answer":
                (
                    "No supporting case or policy "
                    "evidence was retrieved, so I "
                    "cannot answer the question."
                ),

            "cited_ids":
                [],

            "case_cited_ids":
                [],

            "policy_cited_ids":
                [],

            "invalid_citations":
                [],

            "validation_passed":
                False,

            "model":
                None,
        }

    allowed_ids = {
        citation_id_for_document(
            document
        )
        for document in documents
    }

    api_key = os.getenv(
        "MISTRAL_API_KEY"
    )

    if not api_key:

        return {
            "answer":
                (
                    "MISTRAL_API_KEY is not set. "
                    "Retrieval succeeded, but LLM "
                    "generation was skipped."
                ),

            "cited_ids":
                [],

            "case_cited_ids":
                [],

            "policy_cited_ids":
                [],

            "invalid_citations":
                [],

            "validation_passed":
                False,

            "model":
                None,
        }

    model_name = os.getenv(
        "GS_LLM_MODEL",
        "mistral-small-latest",
    )

    context = build_context(
        documents
    )

    user_prompt = f"""
RETRIEVED EVIDENCE

{context}

QUESTION

{question}

Provide a concise investigation answer.

For case-specific factual claims, cite CASE evidence IDs.

For regulatory or policy claims, cite POLICY evidence IDs.

Do not cite an ID unless that evidence directly supports the claim.
"""

    client = Mistral(
        api_key=api_key
    )

    response = (
        client.chat.complete(
            model=model_name,

            messages=[
                {
                    "role":
                        "system",

                    "content":
                        SYSTEM_PROMPT,
                },
                {
                    "role":
                        "user",

                    "content":
                        user_prompt,
                },
            ],
        )
    )

    answer = str(
        response
        .choices[0]
        .message
        .content
    )

    cited_ids = (
        extract_citations(
            answer
        )
    )

    invalid = [
        citation
        for citation in cited_ids
        if citation not in allowed_ids
    ]

    case_cited_ids = [
        citation
        for citation in cited_ids
        if citation.startswith(
            "EVID_"
        )
    ]

    policy_cited_ids = [
        citation
        for citation in cited_ids
        if citation.startswith(
            "POLICY:"
        )
    ]

    passed = (
        len(cited_ids) > 0
        and len(invalid) == 0
    )

    return {
        "answer":
            answer,

        "cited_ids":
            cited_ids,

        "case_cited_ids":
            case_cited_ids,

        "policy_cited_ids":
            policy_cited_ids,

        "invalid_citations":
            invalid,

        "allowed_citation_ids":
            sorted(
                allowed_ids
            ),

        "validation_passed":
            passed,

        "model":
            model_name,
    }
