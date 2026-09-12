from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = PROJECT_ROOT / "reports" / "v2" / "phase13" / "performance_monitor_v1_report.json"

VALID_LABEL_SOURCES = {
    "adjudicated_outcome",
    "authoritative_outcome",
    "confirmed_case_outcome",
}


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]
    raise ValueError("Performance input must be a JSON list, {'records': [...]}, or JSONL.")


def _valid_record(row: dict[str, Any]) -> bool:
    source = str(row.get("label_source", "")).strip().lower()
    if source not in VALID_LABEL_SOURCES:
        return False
    y_true = row.get("y_true")
    y_score = row.get("y_score")
    if y_true not in (0, 1, False, True):
        return False
    if not isinstance(y_score, (int, float)):
        return False
    return 0.0 <= float(y_score) <= 1.0


def _brier(rows: Iterable[dict[str, Any]]) -> float:
    vals = [(float(r["y_score"]) - int(bool(r["y_true"]))) ** 2 for r in rows]
    return sum(vals) / len(vals)


def _log_loss(rows: Iterable[dict[str, Any]]) -> float:
    eps = 1e-12
    vals = []
    for r in rows:
        y = int(bool(r["y_true"]))
        p = min(max(float(r["y_score"]), eps), 1.0 - eps)
        vals.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
    return sum(vals) / len(vals)


def _mean_score(rows: list[dict[str, Any]], target: int) -> float | None:
    vals = [float(r["y_score"]) for r in rows if int(bool(r["y_true"])) == target]
    return None if not vals else sum(vals) / len(vals)


def build_performance_monitor(
    *,
    records: list[dict[str, Any]] | None = None,
    records_path: Path | None = None,
    minimum_valid_labels: int = 30,
    output_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    if records is None:
        records = _load_records(records_path) if records_path else []

    valid = [r for r in records if _valid_record(r)]
    invalid_count = len(records) - len(valid)
    enough = len(valid) >= minimum_valid_labels

    metrics = None
    if enough:
        metrics = {
            "brier_score": _brier(valid),
            "log_loss": _log_loss(valid),
            "mean_score_positive": _mean_score(valid, 1),
            "mean_score_negative": _mean_score(valid, 0),
        }

    report = {
        "schema_version": "phase13_performance_monitor_v1",
        "status": "MONITORED" if enough else "INSUFFICIENT_VALID_LABELS",
        "input_record_count": len(records),
        "valid_labeled_record_count": len(valid),
        "invalid_or_unapproved_record_count": invalid_count,
        "minimum_valid_labels": minimum_valid_labels,
        "metrics": metrics,
        "label_contract": {
            "analyst_feedback_is_not_ground_truth": True,
            "accepted_label_sources": sorted(VALID_LABEL_SOURCES),
            "only_adjudicated_or_authoritative_outcomes_are_eligible": True,
        },
        "governance": {
            "automatic_retraining_triggered": False,
            "automatic_recalibration_triggered": False,
            "automatic_model_promotion": False,
            "automatic_threshold_change": False,
            "human_review_required": True,
            "certified_phase10_model_modified": False,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, default=None)
    parser.add_argument("--minimum-valid-labels", type=int, default=30)
    args = parser.parse_args()

    report = build_performance_monitor(
        records_path=args.records,
        minimum_valid_labels=args.minimum_valid_labels,
    )
    print(json.dumps(report, indent=2))
    print("GRAPHSHIELD_PHASE13_PERFORMANCE_MONITOR=PASS")


if __name__ == "__main__":
    main()
