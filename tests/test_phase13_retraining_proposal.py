import json
from pathlib import Path

from governance.phase13_retraining_proposal import build_retraining_review_proposal


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_proposal_refuses_when_feedback_is_insufficient(tmp_path: Path) -> None:
    gate = tmp_path / "gate.json"
    status = tmp_path / "status.json"
    inv = tmp_path / "inv.json"
    perf = tmp_path / "perf.json"
    out = tmp_path / "proposal.json"

    _write(gate, {"eligible_feedback_count": 0})
    _write(status, {"feedback": {"approved_for_modeling": 0}})
    _write(inv, {"recommended_next_action": "human_drift_investigation"})
    _write(perf, {"status": "INSUFFICIENT_VALID_LABELS"})

    report = build_retraining_review_proposal(
        minimum_feedback=100,
        gate_path=gate,
        status_path=status,
        investigation_path=inv,
        performance_path=perf,
        output_path=out,
    )
    assert report["proposal_status"] == "NOT_READY"
    assert report["retraining_review_may_be_prepared"] is False
    assert report["execution"]["training_started"] is False
    assert report["governance"]["automatic_retraining_allowed"] is False


def test_ready_means_human_review_only_not_training(tmp_path: Path) -> None:
    gate = tmp_path / "gate.json"
    status = tmp_path / "status.json"
    inv = tmp_path / "inv.json"
    perf = tmp_path / "perf.json"
    out = tmp_path / "proposal.json"

    _write(gate, {"eligible_feedback_count": 120})
    _write(status, {"feedback": {"approved_for_modeling": 120}})
    _write(inv, {"recommended_next_action": "human_drift_investigation"})
    _write(perf, {"status": "MONITORED"})

    report = build_retraining_review_proposal(
        minimum_feedback=100,
        gate_path=gate,
        status_path=status,
        investigation_path=inv,
        performance_path=perf,
        output_path=out,
    )
    assert report["proposal_status"] == "READY_FOR_HUMAN_REVIEW"
    assert report["human_approval"]["required"] is True
    assert report["human_approval"]["received"] is False
    assert all(value is False for value in report["execution"].values())
