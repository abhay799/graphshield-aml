from __future__ import annotations

from pathlib import Path

import polars as pl

from explainability.explanation_evidence import (
    Phase11ExplanationEvidenceService,
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
        ).get_column("transaction_id")[0]
    )


def test_phase11_evidence_documents_are_stable_and_label_free():
    txid = _transaction_id()

    service = (
        Phase11ExplanationEvidenceService()
    )

    first = service.build_documents(
        txid,
        top_k=3,
    )

    second = service.build_documents(
        txid,
        top_k=3,
    )

    assert len(first) == 4
    assert [
        item["evidence_id"]
        for item in first
    ] == [
        item["evidence_id"]
        for item in second
    ]

    assert len(
        {
            item["evidence_id"]
            for item in first
        }
    ) == 4

    for item in first:
        assert item["evidence_id"].startswith(
            "EVID_"
        )
        assert item["transaction_id"] == txid
        assert item["governance"][
            "ground_truth_label_exposed"
        ] is False

        lowered = item["content"].lower()

        assert '"is_laundering"' not in lowered
        assert '"ground_truth"' not in lowered


def test_phase11_evidence_documents_are_decision_support_only():
    docs = (
        Phase11ExplanationEvidenceService()
        .build_documents(
            _transaction_id(),
            top_k=3,
        )
    )

    for item in docs:
        governance = item["governance"]

        assert governance["mode"] == (
            "decision_support_only"
        )
        assert governance[
            "human_review_required"
        ] is True
        assert governance[
            "autonomous_account_blocking"
        ] is False
        assert governance[
            "autonomous_case_closure"
        ] is False
        assert governance[
            "autonomous_regulatory_filing"
        ] is False
