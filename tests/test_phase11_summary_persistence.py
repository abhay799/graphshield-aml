from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from explainability.analyst_summary import (
    Phase11AnalystSummaryService,
)
from explainability.persist_explanation import (
    Phase11ExplanationPersistenceService,
)


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


def _transaction_id() -> str:
    return str(
        pl.read_parquet(
            PREDICTIONS,
            columns=["transaction_id"],
        ).get_column(
            "transaction_id"
        )[0]
    )


def test_phase11_analyst_summary_is_deterministic_and_governed():
    txid = _transaction_id()

    service = (
        Phase11AnalystSummaryService()
    )

    first = service.build(
        txid,
        top_k=3,
    )

    second = service.build(
        txid,
        top_k=3,
    )

    assert (
        first["summary"]
        == second["summary"]
    )

    assert (
        first["schema_version"]
        == "phase11_analyst_summary_v1"
    )

    assert (
        "Human analyst review is required."
        in first["summary"]
    )

    assert first["governance"][
        "ground_truth_label_exposed"
    ] is False

    assert first["governance"][
        "autonomous_regulatory_filing"
    ] is False


def test_phase11_persistence_is_phase11_only_and_label_free():
    txid = _transaction_id()

    result = (
        Phase11ExplanationPersistenceService()
        .persist(
            txid,
            top_k=3,
        )
    )

    path = Path(
        result["path"]
    )

    assert path.exists()

    assert (
        "explanations"
        in path.parts
    )

    assert (
        "phase11"
        in path.parts
    )

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    assert payload[
        "schema_version"
    ] == (
        "phase11_persisted_explanation_v1"
    )

    text = path.read_text(
        encoding="utf-8"
    ).lower()

    assert '"is_laundering"' not in text
    assert '"ground_truth"' not in text

    assert payload[
        "provenance"
    ][
        "certified_phase10_artifacts"
    ] == "read_only"

    assert len(
        payload[
            "evidence_documents"
        ]
    ) == 4
