from __future__ import annotations

import json
from pathlib import Path

from investigation.phase12_audit import (
    append_hash_chained_record,
    verify_hash_chain,
)
from investigation.phase12_grounding import (
    validate_claim_citations,
)


CASE_ID = "EVID_ABCDEF1234567890"
POLICY_ID = "POLICY:fatf_test_p1_c1"


def test_phase12_claim_level_grounding_passes():
    answer = (
        f"The transaction shows prior pair activity [{CASE_ID}]. "
        f"FATF policy context requires human interpretation [{POLICY_ID}]. "
        "Human analyst review is required."
    )

    result = validate_claim_citations(
        answer,
        {
            CASE_ID,
            POLICY_ID,
        },
    )

    assert result["passed"] is True


def test_phase12_claim_level_grounding_fails_uncited_claim():
    answer = (
        f"The transaction shows prior pair activity [{CASE_ID}]. "
        "The customer definitely has suspicious history."
    )

    result = validate_claim_citations(
        answer,
        {
            CASE_ID,
        },
    )

    assert result["passed"] is False
    assert result[
        "uncited_claims"
    ]


def test_phase12_claim_level_grounding_rejects_unknown_id():
    answer = (
        "The transaction shows prior pair activity "
        "[EVID_FFFFFFFFFFFFFFFF]."
    )

    result = validate_claim_citations(
        answer,
        {
            CASE_ID,
        },
    )

    assert result["passed"] is False
    assert result[
        "invalid_citations"
    ] == [
        "EVID_FFFFFFFFFFFFFFFF"
    ]


def test_phase12_hash_chain_detects_tampering(
    tmp_path: Path,
):
    path = (
        tmp_path
        / "audit.jsonl"
    )

    append_hash_chained_record(
        path,
        {
            "run_id": "1",
            "status": "completed",
        },
    )

    append_hash_chained_record(
        path,
        {
            "run_id": "2",
            "status": "completed",
        },
    )

    verified = verify_hash_chain(
        path
    )

    assert verified["valid"] is True
    assert verified[
        "record_count"
    ] == 2

    lines = path.read_text(
        encoding="utf-8"
    ).splitlines()

    first = json.loads(
        lines[0]
    )

    first["payload"]["status"] = (
        "tampered"
    )

    lines[0] = json.dumps(
        first,
        sort_keys=True,
        separators=(",", ":"),
    )

    path.write_text(
        "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )

    verified = verify_hash_chain(
        path
    )

    assert verified["valid"] is False
