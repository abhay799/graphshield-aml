from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

REPORT_DIR = ROOT / "reports" / "v2" / "phase10"

REQUIRED_REPORTS = {
    "graph_calibration": REPORT_DIR / "graph_calibration_v1_report.json",
    "replay_scoring": REPORT_DIR / "replay_scoring_consumer_v1_report.json",
    "live_feature_contract": REPORT_DIR / "live_feature_contract_v1.json",
    "basic_feature_contract": REPORT_DIR / "basic_online_feature_contract_v1.json",
    "online_feature_parity": REPORT_DIR / "online_feature_parity_evolving_v1_report.json",
    "stateful_live_scoring": REPORT_DIR / "stateful_live_scoring_v1_report.json",
    "validation_fusion": REPORT_DIR / "validation_fusion_v1_report.json",
    "fusion_holdout": REPORT_DIR / "validation_fusion_holdout_v1_report.json",
    "fusion_calibration": REPORT_DIR / "fusion_calibration_v1_report.json",
    "locked_test": REPORT_DIR / "locked_test_evaluation_v1.json",
}

TGN_REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "training"
    / "tgn_phase10c"
    / "tgn_metrics.json"
)

REQUIRED_ARTIFACTS = {
    "graph_model": ROOT / "models" / "lightgbm_graph_v1.joblib",
    "graph_calibrator": ROOT / "models" / "probability_calibrator_graph_v1.joblib",
    "tgn_checkpoint": ROOT / "models" / "v2" / "tgn_phase10c" / "tgn_risk.pt",
    "fusion_ecdf": ROOT / "models" / "v2" / "phase10_fusion_ecdf_v1.npz",
    "fusion_calibrator": ROOT / "models" / "v2" / "phase10_fusion_calibrator_v1.joblib",
    "locked_test_predictions": (
        ROOT
        / "data"
        / "processed"
        / "modeling"
        / "v2"
        / "phase10"
        / "locked_test_predictions_v1.parquet"
    ),
}

OUTPUT = REPORT_DIR / "phase10_certification_v1.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    print("=" * 92)
    print("GraphShield AML - Phase 10 Final Certification")
    print("=" * 92)

    missing_reports = [
        str(path)
        for path in [*REQUIRED_REPORTS.values(), TGN_REPORT]
        if not path.exists()
    ]
    require(
        not missing_reports,
        "Missing required Phase 10 report(s):\n" + "\n".join(missing_reports),
    )

    missing_artifacts = [
        str(path)
        for path in REQUIRED_ARTIFACTS.values()
        if not path.exists()
    ]
    require(
        not missing_artifacts,
        "Missing required Phase 10 artifact(s):\n" + "\n".join(missing_artifacts),
    )

    reports = {
        name: load_json(path)
        for name, path in REQUIRED_REPORTS.items()
    }
    tgn = load_json(TGN_REPORT)

    # -----------------------------
    # A: graph calibration/replay
    # -----------------------------
    require(
        reports["graph_calibration"].get("test_used_for_fit") is False
        or reports["graph_calibration"].get("test_used_for_calibration_fit") is False,
        "Graph calibration report does not certify validation-only fitting.",
    )

    # -----------------------------
    # B: online feature/scoring
    # -----------------------------
    feature_contract = reports["live_feature_contract"]
    require(
        feature_contract.get("status") == "PASS",
        "Live feature contract did not PASS.",
    )
    require(
        feature_contract.get("label_used") is False
        or feature_contract.get("label_exposure") is False
        or feature_contract.get("label_leakage") in (None, False, "NONE"),
        "Live feature contract indicates label exposure.",
    )

    basic = reports["basic_feature_contract"]
    require(
        basic.get("status") == "PASS",
        "Basic online feature contract did not PASS.",
    )
    require(
        basic.get("label_used") is False,
        "Basic online feature contract used labels.",
    )

    parity = reports["online_feature_parity"]
    require(
        parity.get("status") == "PASS",
        "Online feature parity did not PASS.",
    )
    require(
        int(parity.get("total_mismatches", 0)) == 0,
        "Online feature parity has mismatches.",
    )
    require(
        parity.get("current_timestamp_state_visible") is False,
        "Current timestamp state leaked into online features.",
    )
    require(
        parity.get("zero_fill_missing_features") is False,
        "Online parity report indicates zero-fill of missing features.",
    )
    require(
        parity.get("label_selected") is False,
        "Online parity selected the target label.",
    )

    live = reports["stateful_live_scoring"]
    require(
        live.get("status") == "PASS",
        "Stateful live scoring did not PASS.",
    )

    # -----------------------------
    # C: TGN selection safety
    # -----------------------------
    require(
        tgn.get("test_evaluated") is False,
        "TGN candidate evaluated test during selection.",
    )
    require(
        tgn.get("final_test") in (None, {}),
        "TGN selection report contains final test metrics.",
    )

    # -----------------------------
    # D: fusion selection/holdout/calibration/test
    # -----------------------------
    fusion = reports["validation_fusion"]
    require(
        fusion.get("status") == "PASS",
        "Validation fusion did not PASS.",
    )
    require(
        fusion.get("locked_test_read") is False,
        "Locked test was read during fusion selection.",
    )
    require(
        fusion.get("test_used_for_selection") is False,
        "Test was used for fusion selection.",
    )

    selected = fusion["selected"]
    graph_weight = float(selected["graph_weight"])
    tgn_weight = float(selected["tgn_weight"])

    require(
        abs(graph_weight + tgn_weight - 1.0) < 1e-12,
        "Fusion weights do not sum to 1.",
    )

    holdout = reports["fusion_holdout"]
    require(
        holdout.get("status") == "PASS",
        "Fusion confirmation holdout did not PASS.",
    )
    require(
        holdout.get("weights_tuned_on_confirmation") is False,
        "Fusion weights were tuned again on confirmation holdout.",
    )
    require(
        holdout.get("locked_test_read") is False,
        "Locked test was read during confirmation holdout.",
    )
    require(
        holdout.get("test_used_for_selection") is False,
        "Test was used during confirmation holdout.",
    )
    require(
        holdout.get("tgn_retrained") is False,
        "TGN was retrained during confirmation holdout.",
    )

    cal = reports["fusion_calibration"]
    require(
        cal.get("status") == "PASS",
        "Fusion calibration did not PASS.",
    )
    require(
        cal.get("fusion_weights_tuned_again") is False,
        "Fusion weights were tuned again during calibration.",
    )
    require(
        cal.get("test_used_for_selection") is False,
        "Test was used for calibration selection.",
    )
    require(
        cal.get("test_used_for_calibration_fit") is False,
        "Test was used for calibration fitting.",
    )

    locked = reports["locked_test"]
    require(
        locked.get("status") == "PASS",
        "Locked test evaluation did not PASS.",
    )
    require(
        locked.get("locked_test_evaluation") is True,
        "Locked-test report does not mark locked test evaluation.",
    )
    require(
        locked.get("model_or_weight_tuning_after_test") is False,
        "Report indicates model/weight tuning after test.",
    )
    require(
        locked.get("calibrator_refit_on_test") is False,
        "Calibrator was refit on test.",
    )
    require(
        locked.get("tgn_retrained_for_test") is False,
        "TGN was retrained for test.",
    )
    require(
        locked.get("test_used_for_selection") is False,
        "Locked test was used for selection.",
    )
    require(
        locked.get("test_used_for_calibration_fit") is False,
        "Locked test was used for calibration fit.",
    )

    graph_metrics = locked["graph_raw"]
    tgn_metrics = locked["tgn"]
    fusion_metrics = locked["fusion_raw"]
    fusion_cal = locked["fusion_calibrated"]

    final_candidate = (
        "graph_tgn_fusion"
        if locked.get("fusion_beats_graph_on_test_ap") is True
        else "lightgbm_graph"
    )

    certification = {
        "status": "PASS",
        "phase": 10,
        "title": "Real-Time Streaming + Temporal Fusion",
        "blocks": {
            "A_replay_scoring_graph_calibration": "PASS",
            "B_online_feature_parity_live_scoring": "PASS",
            "C_stronger_tgn": "PASS",
            "D_fusion_calibration_locked_test": "PASS",
        },
        "frozen_fusion": {
            "graph_weight": graph_weight,
            "tgn_weight": tgn_weight,
            "confirmed_on_validation_holdout": bool(
                holdout.get("fusion_confirmed")
            ),
        },
        "locked_test": {
            "rows": locked.get("rows"),
            "positives": locked.get("positives"),
            "graph_average_precision": graph_metrics.get("average_precision"),
            "graph_recall_at_top_1pct": graph_metrics.get("recall_at_top_1pct"),
            "tgn_average_precision": tgn_metrics.get("average_precision"),
            "tgn_recall_at_top_1pct": tgn_metrics.get("recall_at_top_1pct"),
            "fusion_average_precision": fusion_metrics.get("average_precision"),
            "fusion_recall_at_top_1pct": fusion_metrics.get("recall_at_top_1pct"),
            "fusion_calibrated_brier": fusion_cal.get("brier_score"),
            "fusion_calibrated_ece_10_bins": fusion_cal.get("ece_10_bins"),
            "fusion_ap_delta_vs_graph": locked.get("fusion_ap_delta_vs_graph"),
            "fusion_recall_at_1pct_delta_vs_graph": locked.get(
                "fusion_recall_at_1pct_delta_vs_graph"
            ),
        },
        "final_phase10_candidate": final_candidate,
        "governance": {
            "decision_support_only": True,
            "human_review_required": True,
            "autonomous_blocking": False,
            "autonomous_case_closure": False,
            "autonomous_regulatory_filing": False,
            "test_used_for_selection": False,
            "test_used_for_calibration_fit": False,
            "model_or_weight_tuning_after_test": False,
        },
        "required_reports": {
            key: str(path)
            for key, path in REQUIRED_REPORTS.items()
        },
        "required_artifacts": {
            key: str(path)
            for key, path in REQUIRED_ARTIFACTS.items()
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(certification, indent=2),
        encoding="utf-8",
    )

    print()
    print("=== PHASE 10 FINAL ===")
    print(f"FINAL_CANDIDATE={final_candidate}")
    print(
        "GRAPH_TEST_AP="
        f"{graph_metrics.get('average_precision')}"
    )
    print(
        "TGN_TEST_AP="
        f"{tgn_metrics.get('average_precision')}"
    )
    print(
        "FUSION_TEST_AP="
        f"{fusion_metrics.get('average_precision')}"
    )
    print(
        "FUSION_AP_DELTA_VS_GRAPH="
        f"{locked.get('fusion_ap_delta_vs_graph')}"
    )
    print(
        "FUSION_TEST_RECALL_AT_1PCT="
        f"{fusion_metrics.get('recall_at_top_1pct')}"
    )
    print(
        "FUSION_CALIBRATED_BRIER="
        f"{fusion_cal.get('brier_score')}"
    )
    print(
        "FUSION_CALIBRATED_ECE_10="
        f"{fusion_cal.get('ece_10_bins')}"
    )
    print("TEST_USED_FOR_SELECTION=FALSE")
    print("TEST_USED_FOR_CALIBRATION_FIT=FALSE")
    print("MODEL_OR_WEIGHT_TUNING_AFTER_TEST=FALSE")
    print("DECISION_SUPPORT_ONLY=TRUE")
    print("HUMAN_REVIEW_REQUIRED=TRUE")
    print(f"REPORT={OUTPUT}")
    print("GRAPHSHIELD_PHASE10_CERTIFICATION=PASS")


if __name__ == "__main__":
    main()
