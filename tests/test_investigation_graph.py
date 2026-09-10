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


def test_investigation_snapshot():

    case_id = top_case()

    response = client.get(
        f"/cases/{case_id}/snapshot"
    )

    assert (
        response.status_code
        == 200
    )

    payload = response.json()

    for key in (
        "case",
        "overview",
        "paths",
        "history",
    ):

        assert key in payload


def test_case_graph_contract():

    case_id = top_case()

    response = client.get(
        f"/cases/{case_id}/graph"
        "?max_edges=50"
    )

    assert (
        response.status_code
        == 200
    )

    payload = response.json()

    assert payload[
        "materialized"
    ] is True

    assert payload[
        "displayed_nodes"
    ] >= 2

    assert payload[
        "displayed_edges"
    ] >= 1

    assert payload[
        "source_column"
    ] == "from_account_key"

    assert payload[
        "target_column"
    ] == "to_account_key"


def test_graph_contains_focal_transaction():

    case_id = top_case()

    response = client.get(
        f"/cases/{case_id}/graph"
        "?max_edges=100"
    )

    assert (
        response.status_code
        == 200
    )

    edges = response.json()[
        "edges"
    ]

    focal = [
        edge
        for edge in edges
        if edge.get(
            "is_focal"
        )
    ]

    assert focal
