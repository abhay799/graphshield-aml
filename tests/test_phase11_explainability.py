from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.explainability_routes import router


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PREDICTIONS = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "phase10"
    / "locked_test_predictions_v1.parquet"
)

CASE_QUEUE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _contains_forbidden_key(value) -> bool:
    forbidden = {
        "is_laundering",
        "ground_truth",
        "label",
        "target",
    }

    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in forbidden:
                return True
            if _contains_forbidden_key(child):
                return True

    elif isinstance(value, list):
        return any(
            _contains_forbidden_key(item)
            for item in value
        )

    return False


def test_phase11_transaction_explanation_endpoint():
    txid = str(
        pl.read_parquet(
            PREDICTIONS,
            columns=["transaction_id"],
        ).get_column("transaction_id")[0]
    )

    response = _client().get(
        f"/explainability/transactions/{txid}",
        params={"top_k": 3},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["schema_version"] == (
        "phase11_explanation_bundle_v1"
    )
    assert body["transaction_id"] == txid
    assert body["governance"]["mode"] == (
        "decision_support_only"
    )
    assert body["governance"][
        "human_review_required"
    ] is True
    assert body["governance"][
        "certified_phase10_artifacts"
    ] == "read_only"
    assert not _contains_forbidden_key(body)


def test_phase11_transaction_explanation_not_found():
    response = _client().get(
        "/explainability/transactions/"
        "DOES_NOT_EXIST_PHASE11"
    )

    assert response.status_code == 404


def test_phase11_case_explanation_endpoint_if_available():
    if not CASE_QUEUE.exists():
        pytest.skip("Case queue unavailable.")

    schema = pl.read_parquet_schema(CASE_QUEUE)
    names = set(schema.names())

    case_column = next(
        (
            name
            for name in (
                "case_id",
                "investigation_id",
                "alert_id",
            )
            if name in names
        ),
        None,
    )

    transaction_column = next(
        (
            name
            for name in (
                "transaction_id",
                "focal_transaction_id",
            )
            if name in names
        ),
        None,
    )

    if case_column is None or transaction_column is None:
        pytest.skip("Unsupported case queue schema.")

    # Keep this overlap lookup inside Polars. Materializing the full prediction
    # ID column (~761k rows) into a Python set can exhaust memory in a full-suite
    # run and trigger a PyO3 panic even though the application behavior is fine.
    candidates = (
        pl.scan_parquet(CASE_QUEUE)
        .select(
            pl.col(case_column).cast(pl.String),
            pl.col(transaction_column).cast(pl.String),
        )
    )
    predictions = (
        pl.scan_parquet(PREDICTIONS)
        .select(pl.col("transaction_id").cast(pl.String))
        .unique()
    )
    match_frame = (
        candidates.join(
            predictions,
            left_on=transaction_column,
            right_on="transaction_id",
            how="semi",
        )
        .limit(1)
        .collect()
    )

    if match_frame.is_empty():
        pytest.skip(
            "No case queue transaction overlaps the "
            "locked Phase 10 prediction artifact."
        )

    case_id = str(match_frame.row(0, named=True)[case_column])

    response = _client().get(
        f"/explainability/cases/{case_id}",
        params={"top_k": 3},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["schema_version"] == (
        "phase11_case_explanation_v1"
    )
    assert body["case_id"] == case_id
    assert body["governance"][
        "case_queue"
    ] == "read_only"
    assert not _contains_forbidden_key(body)
