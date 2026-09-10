from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app


client = TestClient(
    app
)


def top_case() -> str:

    response = client.get(
        "/cases?limit=1"
    )

    assert (
        response.status_code
        == 200
    )

    return response.json()[
        "cases"
    ][0][
        "case_id"
    ]


def test_unified_intelligence_without_policy():

    case_id = top_case()

    response = client.post(
        f"/cases/{case_id}/intelligence",
        json={
            "question":
                None,

            "include_policy":
                False,
        },
    )

    assert (
        response.status_code
        == 200
    )

    payload = response.json()

    required = (
        "case",
        "graph",
        "investigation",
        "retrieval",
        "analyst",
        "governance",
    )

    for key in required:

        assert key in payload

    assert payload[
        "case_id"
    ] == case_id

    assert payload[
        "governance"
    ][
        "human_review_required"
    ] is True

    assert payload[
        "governance"
    ][
        "autonomous_regulatory_filing"
    ] is False


def test_invalid_intelligence_top_k():

    case_id = top_case()

    response = client.post(
        f"/cases/{case_id}/intelligence",
        json={
            "evidence_top_k":
                1000
        },
    )

    assert (
        response.status_code
        == 422
    )


def test_invalid_analyst_status_rejected():

    case_id = top_case()

    response = client.put(
        f"/analyst/cases/"
        f"{case_id}/state",
        json={
            "review_status":
                "AUTO_BLOCK_ACCOUNT",

            "analyst_note":
                "Regression safety test",

            "actor":
                "pytest",
        },
    )

    assert (
        response.status_code
        == 400
    )


def test_unknown_analyst_case_rejected():

    response = client.get(
        "/analyst/cases/"
        "CASE_DOES_NOT_EXIST/state"
    )

    assert (
        response.status_code
        == 404
    )
