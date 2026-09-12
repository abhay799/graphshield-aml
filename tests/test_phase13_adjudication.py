from __future__ import annotations

from pathlib import Path

from governance.feedback_adjudication import (
    Phase13FeedbackAdjudicationStore,
)
from governance.feedback_store import (
    Phase13FeedbackStore,
)


def test_phase13_adjudication_is_append_only(
    tmp_path: Path,
):
    db = (
        tmp_path
        / "feedback.duckdb"
    )

    feedback_store = (
        Phase13FeedbackStore(
            db_path=db,
            audit_path=(
                tmp_path
                / "feedback_audit.jsonl"
            ),
        )
    )

    feedback = (
        feedback_store.add_feedback(
            case_id="CASE_1",
            transaction_id="TX_1",
            analyst_outcome=
                "needs_more_information",
            confidence=0.8,
            rationale=
                "More evidence required.",
            analyst_id=
                "analyst_one",
        )
    )

    adjudication_store = (
        Phase13FeedbackAdjudicationStore(
            db_path=db,
            audit_path=(
                tmp_path
                / "adjudication_audit.jsonl"
            ),
        )
    )

    event = (
        adjudication_store.adjudicate(
            feedback_id=
                feedback.feedback_id,
            reviewer_id=
                "reviewer_one",
            decision=
                "approved_for_modeling",
            rationale=
                "Second review completed.",
        )
    )

    assert event.modeling_eligible is True

    latest = (
        adjudication_store
        .latest_adjudication(
            feedback.feedback_id
        )
    )

    assert latest is not None

    assert (
        latest["decision"]
        == "approved_for_modeling"
    )

    assert (
        feedback.feedback_id
        in adjudication_store
        .approved_feedback_ids()
    )


def test_phase13_rejected_adjudication_is_not_modeling_eligible(
    tmp_path: Path,
):
    db = (
        tmp_path
        / "feedback.duckdb"
    )

    feedback = (
        Phase13FeedbackStore(
            db_path=db,
            audit_path=(
                tmp_path
                / "feedback_audit.jsonl"
            ),
        )
        .add_feedback(
            case_id="CASE_2",
            analyst_outcome=
                "dismiss_alert",
            confidence=0.9,
            rationale=
                "Reviewed and dismissed.",
            analyst_id=
                "analyst_two",
        )
    )

    store = (
        Phase13FeedbackAdjudicationStore(
            db_path=db,
            audit_path=(
                tmp_path
                / "adjudication_audit.jsonl"
            ),
        )
    )

    event = store.adjudicate(
        feedback_id=
            feedback.feedback_id,
        reviewer_id=
            "reviewer_two",
        decision=
            "rejected_for_modeling",
        rationale=
            "Not suitable as a modeling label.",
    )

    assert event.modeling_eligible is False

    assert (
        feedback.feedback_id
        not in store
        .approved_feedback_ids()
    )
