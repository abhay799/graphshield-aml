from pathlib import Path

from governance.phase13_performance_monitor import build_performance_monitor


def test_feedback_without_approved_label_source_is_not_truth(tmp_path: Path) -> None:
    report = build_performance_monitor(
        records=[
            {"y_true": 1, "y_score": 0.9, "label_source": "analyst_feedback"},
            {"y_true": 0, "y_score": 0.1, "label_source": "raw_feedback"},
        ],
        minimum_valid_labels=1,
        output_path=tmp_path / "report.json",
    )
    assert report["status"] == "INSUFFICIENT_VALID_LABELS"
    assert report["valid_labeled_record_count"] == 0
    assert report["metrics"] is None
    assert report["governance"]["automatic_retraining_triggered"] is False


def test_valid_adjudicated_outcomes_can_be_monitored(tmp_path: Path) -> None:
    report = build_performance_monitor(
        records=[
            {"y_true": 1, "y_score": 0.9, "label_source": "adjudicated_outcome"},
            {"y_true": 0, "y_score": 0.2, "label_source": "authoritative_outcome"},
        ],
        minimum_valid_labels=2,
        output_path=tmp_path / "report.json",
    )
    assert report["status"] == "MONITORED"
    assert report["valid_labeled_record_count"] == 2
    assert report["metrics"]["brier_score"] >= 0
    assert report["governance"]["automatic_model_promotion"] is False
