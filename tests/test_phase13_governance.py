from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from governance.feedback_store import (
    Phase13FeedbackStore,
)
from governance.phase13_drift_monitor import (
    categorical_tvd,
    numeric_psi,
)


def test_phase13_feedback_is_append_only_and_not_training_label_by_default(
    tmp_path: Path,
):
    store = Phase13FeedbackStore(
        db_path=tmp_path / "feedback.duckdb",
        audit_path=tmp_path / "audit.jsonl",
    )

    event = store.add_feedback(
        case_id="CASE_1",
        transaction_id="TX_1",
        analyst_outcome="needs_more_information",
        confidence=0.75,
        rationale="Additional counterparty context required.",
        analyst_id="analyst_test",
    )

    assert event.modeling_eligible is False
    assert event.adjudication_status == "pending"

    rows = store.list_case_feedback(
        "CASE_1"
    )

    assert len(rows) == 1

    assert (
        store.modeling_eligible_feedback()
        == []
    )


def test_phase13_modeling_eligible_requires_adjudication(
    tmp_path: Path,
):
    store = Phase13FeedbackStore(
        db_path=tmp_path / "feedback.duckdb",
        audit_path=tmp_path / "audit.jsonl",
    )

    with pytest.raises(
        ValueError
    ):
        store.add_feedback(
            case_id="CASE_1",
            analyst_outcome="dismiss_alert",
            confidence=0.9,
            rationale="Reviewed evidence.",
            analyst_id="analyst_test",
            modeling_eligible=True,
            adjudication_status="pending",
        )


def test_phase13_numeric_psi_detects_distribution_shift():
    reference = pd.Series(
        list(range(1000))
    )

    same = pd.Series(
        list(range(1000))
    )

    shifted = pd.Series(
        list(range(1000, 2000))
    )

    assert numeric_psi(
        reference,
        same,
    ) < 1e-9

    assert numeric_psi(
        reference,
        shifted,
    ) > 0.25


def test_phase13_categorical_tvd_detects_shift_and_unseen_categories():
    reference = pd.Series(
        ["A"] * 80
        + ["B"] * 20
    )

    monitor = pd.Series(
        ["A"] * 20
        + ["B"] * 20
        + ["C"] * 60
    )

    distance, unseen = (
        categorical_tvd(
            reference,
            monitor,
        )
    )

    assert distance > 0.25
    assert unseen == 0.60
