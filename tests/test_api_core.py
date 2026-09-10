from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app


client = TestClient(
    app
)


def get_top_case_id() -> str:

    response = client.get(
        "/cases?limit=1"
    )

    assert (
        response.status_code
        == 200
    )

    payload = response.json()

    assert payload[
        "count"
    ] == 1

    assert len(
        payload[
            "cases"
        ]
    ) == 1

    return payload[
        "cases"
    ][0][
        "case_id"
    ]


def test_root_endpoint():

    response = client.get(
        "/"
    )

    assert (
        response.status_code
        == 200
    )


def test_health_contract():

    response = client.get(
        "/health"
    )

    assert (
        response.status_code
        == 200
    )

    payload = response.json()

    assert payload[
        "status"
    ] == "ok"

    assert payload[
        "case_queue_rows"
    ] == 7617

    assert payload[
        "champion"
    ] == "lightgbm_graph"


def test_governance_contract():

    response = client.get(
        "/governance"
    )

    assert (
        response.status_code
        == 200
    )

    payload = response.json()

    assert payload[
        "human_review_required"
    ] is True

    assert payload[
        "autonomous_account_blocking"
    ] is False

    assert payload[
        "autonomous_case_closure"
    ] is False

    assert payload[
        "autonomous_regulatory_filing"
    ] is False


def test_case_queue_contract():

    response = client.get(
        "/cases?limit=5"
    )

    assert (
        response.status_code
        == 200
    )

    payload = response.json()

    assert payload[
        "count"
    ] == 5

    assert len(
        payload[
            "cases"
        ]
    ) == 5


def test_case_lookup_contract():

    case_id = (
        get_top_case_id()
    )

    response = client.get(
        f"/cases/{case_id}"
    )

    assert (
        response.status_code
        == 200
    )

    payload = response.json()

    assert payload[
        "case_id"
    ] == case_id

    assert payload[
        "source_model"
    ] == "lightgbm_graph"


def test_unknown_case_returns_404():

    response = client.get(
        "/cases/"
        "CASE_DOES_NOT_EXIST"
    )

    assert (
        response.status_code
        == 404
    )
