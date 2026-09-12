from __future__ import annotations

import numpy as np

from governance.phase13_governance_gate import (
    evaluate_governance_gate,
)
from governance.phase13_score_drift import (
    numeric_psi,
)


def test_phase13_score_psi_is_zero_for_same_distribution():
    values = np.linspace(
        0.0,
        1.0,
        1000,
    )

    assert numeric_psi(
        values,
        values,
    ) < 1e-9


def test_phase13_score_psi_detects_shift():
    reference = np.linspace(
        0.0,
        0.2,
        1000,
    )

    monitor = np.linspace(
        0.8,
        1.0,
        1000,
    )

    assert numeric_psi(
        reference,
        monitor,
    ) > 0.25


def test_phase13_gate_never_auto_retrains():
    gate = evaluate_governance_gate(
        feature_severity="critical",
        score_severity="critical",
        eligible_feedback_count=10_000,
        minimum_feedback_for_retraining_review=100,
    )

    assert gate[
        "retraining_review_may_be_prepared"
    ] is True

    assert gate[
        "automatic_retraining_allowed"
    ] is False

    assert gate[
        "automatic_model_promotion_allowed"
    ] is False

    assert gate[
        "automatic_threshold_change_allowed"
    ] is False

    assert gate[
        "human_approval_required"
    ] is True


def test_phase13_gate_does_not_recommend_retraining_without_adjudicated_feedback():
    gate = evaluate_governance_gate(
        feature_severity="critical",
        score_severity="stable",
        eligible_feedback_count=0,
        minimum_feedback_for_retraining_review=100,
    )

    assert gate[
        "retraining_review_may_be_prepared"
    ] is False

    assert gate[
        "recommended_action"
    ] == "investigate_critical_drift"
