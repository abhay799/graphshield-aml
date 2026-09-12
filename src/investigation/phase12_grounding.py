from __future__ import annotations

import re
from typing import Any


CASE_PATTERN = re.compile(
    r"\[(EVID_[A-F0-9]{16})\]"
)

POLICY_PATTERN = re.compile(
    r"\[(POLICY:[A-Za-z0-9_.:-]+)\]"
)

ANY_CITATION_PATTERN = re.compile(
    r"\[(EVID_[A-F0-9]{16}|POLICY:[A-Za-z0-9_.:-]+)\]"
)

SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?])\s+|\n+"
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

NON_FACTUAL_ALLOWED = (
    "human analyst review is required",
    "this is not legal advice",
    "this does not establish",
    "these indicators are not proof",
    "insufficient evidence",
    "cannot answer",
)


def citation_ids(
    text: str,
) -> list[str]:
    return sorted(
        set(
            ANY_CITATION_PATTERN.findall(
                text
            )
        )
    )


def _clean_claims(
    answer: str,
) -> list[str]:
    claims = []

    for part in SENTENCE_SPLIT.split(
        answer.strip()
    ):
        text = part.strip(
            " \t\r\n-*#"
        )

        if not text:
            continue

        if len(
            text.split()
        ) < 3:
            continue

        claims.append(
            text
        )

    return claims


def _policy_like(
    claim: str,
) -> bool:
    lowered = claim.lower()

    return any(
        term in lowered
        for term in POLICY_TERMS
    )


def _allowed_without_citation(
    claim: str,
) -> bool:
    lowered = claim.lower()

    return any(
        phrase in lowered
        for phrase in NON_FACTUAL_ALLOWED
    )


def validate_claim_citations(
    answer: str,
    allowed_ids: set[str],
) -> dict[str, Any]:
    """
    Strict claim-level grounding validation.

    Rules:
    - every substantive factual sentence needs at least one citation;
    - every citation must exist in retrieved evidence;
    - policy-like claims need at least one POLICY citation;
    - non-policy factual claims need at least one CASE/Phase11 EVID citation;
    - limited governance/insufficiency sentences may be uncited.
    """

    claims = _clean_claims(
        answer
    )

    claim_reports = []
    uncited_claims = []
    invalid_citations = []
    citation_type_mismatches = []

    for claim in claims:
        cited = citation_ids(
            claim
        )

        invalid = [
            item
            for item in cited
            if item not in allowed_ids
        ]

        if invalid:
            invalid_citations.extend(
                invalid
            )

        policy_like = _policy_like(
            claim
        )

        case_ids = [
            item
            for item in cited
            if item.startswith(
                "EVID_"
            )
        ]

        policy_ids = [
            item
            for item in cited
            if item.startswith(
                "POLICY:"
            )
        ]

        allowed_uncited = (
            _allowed_without_citation(
                claim
            )
        )

        if (
            not cited
            and not allowed_uncited
        ):
            uncited_claims.append(
                claim
            )

        type_ok = True

        if cited:
            if (
                policy_like
                and not policy_ids
            ):
                type_ok = False
            elif (
                not policy_like
                and not case_ids
            ):
                type_ok = False

        if not type_ok:
            citation_type_mismatches.append(
                claim
            )

        claim_reports.append(
            {
                "claim": claim,
                "citations": cited,
                "policy_like": policy_like,
                "allowed_uncited":
                    allowed_uncited,
                "invalid_citations":
                    invalid,
                "citation_type_ok":
                    type_ok,
            }
        )

    unique_invalid = sorted(
        set(
            invalid_citations
        )
    )

    passed = (
        len(claims) > 0
        and not uncited_claims
        and not unique_invalid
        and not citation_type_mismatches
    )

    return {
        "passed": passed,
        "claim_count": len(
            claims
        ),
        "uncited_claims":
            uncited_claims,
        "invalid_citations":
            unique_invalid,
        "citation_type_mismatches":
            citation_type_mismatches,
        "claim_reports":
            claim_reports,
    }
