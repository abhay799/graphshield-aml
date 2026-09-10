from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.append(
    str(
        PROJECT_ROOT
        / "src"
    )
)


from retrieval.grounded_llm import (
    build_context,
    citation_id_for_document,
    extract_citations,
)


CASE_DOC = {
    "evidence_id":
        "EVID_AB12CD34EF56AB78",

    "source_type":
        "focal_transaction",

    "source_ref":
        "TX_TEST_001",

    "content":
        (
            "The focal transaction was "
            "USD 10,000 from account A "
            "to account B."
        ),
}


POLICY_DOC = {
    "chunk_id":
        "fatf_recommendations_2026_p0022_c001",

    "authority":
        "Financial Action Task Force",

    "title":
        "The FATF Recommendations",

    "jurisdiction":
        "International",

    "version":
        "June 2026",

    "page_number":
        22,

    "source_url":
        "https://www.fatf-gafi.org/",

    "content":
        (
            "Financial institutions should "
            "perform customer due diligence "
            "and ongoing monitoring."
        ),
}


def validate(
    answer,
    documents,
):

    allowed = {
        citation_id_for_document(
            document
        )
        for document
        in documents
    }

    cited = extract_citations(
        answer
    )

    invalid = [
        citation
        for citation in cited
        if citation not in allowed
    ]

    passed = (
        len(cited) > 0
        and len(invalid) == 0
    )

    return {
        "cited":
            cited,

        "invalid":
            invalid,

        "passed":
            passed,
    }


def assert_test(
    name,
    condition,
):

    if not condition:

        print(
            f"FAIL - {name}"
        )

        raise SystemExit(1)

    print(
        f"PASS - {name}"
    )


def main():

    documents = [
        CASE_DOC,
        POLICY_DOC,
    ]

    print(
        "=" * 90
    )

    print(
        "GraphShield AML - "
        "Grounded Citation Validator"
    )

    print(
        "=" * 90
    )

    # --------------------------------------------------
    # Test 1: valid CASE citation
    # --------------------------------------------------

    result = validate(
        (
            "The transaction was USD 10,000 "
            "[EVID_AB12CD34EF56AB78]."
        ),
        documents,
    )

    assert_test(
        "valid case citation accepted",
        result["passed"],
    )

    # --------------------------------------------------
    # Test 2: valid POLICY citation
    # --------------------------------------------------

    result = validate(
        (
            "The retrieved FATF guidance "
            "discusses customer due diligence "
            "[POLICY:"
            "fatf_recommendations_2026_"
            "p0022_c001]."
        ),
        documents,
    )

    assert_test(
        "valid policy citation accepted",
        result["passed"],
    )

    # --------------------------------------------------
    # Test 3: mixed valid citations
    # --------------------------------------------------

    result = validate(
        (
            "The case contains the focal "
            "transaction "
            "[EVID_AB12CD34EF56AB78]. "
            "The retrieved FATF material "
            "contains relevant CDD guidance "
            "[POLICY:"
            "fatf_recommendations_2026_"
            "p0022_c001]."
        ),
        documents,
    )

    assert_test(
        "mixed case + policy citations accepted",
        result["passed"],
    )

    # --------------------------------------------------
    # Test 4: fabricated CASE citation
    # --------------------------------------------------

    result = validate(
        (
            "Unsupported case claim "
            "[EVID_FFFFFFFFFFFFFFFF]."
        ),
        documents,
    )

    assert_test(
        "fabricated case citation rejected",
        not result["passed"],
    )

    # --------------------------------------------------
    # Test 5: fabricated POLICY citation
    # --------------------------------------------------

    result = validate(
        (
            "Unsupported policy claim "
            "[POLICY:"
            "fake_policy_document_p9999_c999]."
        ),
        documents,
    )

    assert_test(
        "fabricated policy citation rejected",
        not result["passed"],
    )

    # --------------------------------------------------
    # Test 6: uncited answer
    # --------------------------------------------------

    result = validate(
        "This answer contains no citation.",
        documents,
    )

    assert_test(
        "uncited answer rejected",
        not result["passed"],
    )

    # --------------------------------------------------
    # Context metadata check
    # --------------------------------------------------

    context = build_context(
        documents
    )

    assert_test(
        "policy authority preserved",
        (
            "Financial Action Task Force"
            in context
        ),
    )

    assert_test(
        "policy version preserved",
        "June 2026" in context,
    )

    assert_test(
        "policy page preserved",
        "Page: 22" in context,
    )

    assert_test(
        "policy chunk ID preserved",
        (
            "fatf_recommendations_2026_"
            "p0022_c001"
            in context
        ),
    )

    print()
    print(
        "GROUNDING CITATION VALIDATOR: PASS"
    )


if __name__ == "__main__":
    main()
