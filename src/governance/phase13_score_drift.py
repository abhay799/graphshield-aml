from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


GOLD_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

GRAPH_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "lightgbm_graph_v1.joblib"
)

GRAPH_CALIBRATOR_PATH = (
    PROJECT_ROOT
    / "models"
    / "probability_calibrator_graph_v1.joblib"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase13"
    / "score_drift_v1_report.json"
)

EPSILON = 1e-6


def _severity(value: float) -> str:
    if value < 0.10:
        return "stable"
    if value < 0.25:
        return "warning"
    return "critical"


def numeric_psi(
    reference: np.ndarray,
    monitor: np.ndarray,
    bins: int = 10,
) -> float:
    reference = np.asarray(
        reference,
        dtype=float,
    )

    monitor = np.asarray(
        monitor,
        dtype=float,
    )

    reference = reference[
        np.isfinite(reference)
    ]

    monitor = monitor[
        np.isfinite(monitor)
    ]

    if (
        reference.size == 0
        or monitor.size == 0
    ):
        return 0.0

    edges = np.unique(
        np.quantile(
            reference,
            np.linspace(
                0.0,
                1.0,
                bins + 1,
            ),
        )
    )

    if len(edges) < 3:
        return 0.0

    edges = edges.astype(float)
    edges[0] = -np.inf
    edges[-1] = np.inf

    ref_counts, _ = np.histogram(
        reference,
        bins=edges,
    )

    mon_counts, _ = np.histogram(
        monitor,
        bins=edges,
    )

    ref_prop = (
        ref_counts.astype(float)
        / max(
            ref_counts.sum(),
            1,
        )
    )

    mon_prop = (
        mon_counts.astype(float)
        / max(
            mon_counts.sum(),
            1,
        )
    )

    ref_prop = np.clip(
        ref_prop,
        EPSILON,
        None,
    )

    mon_prop = np.clip(
        mon_prop,
        EPSILON,
        None,
    )

    return float(
        np.sum(
            (
                mon_prop
                - ref_prop
            )
            * np.log(
                mon_prop
                / ref_prop
            )
        )
    )


class Phase13ScoreDriftMonitor:
    """
    Frozen-model score-distribution monitor.

    Reference window: validation.
    Monitoring simulation window: test.

    This does NOT tune, retrain, recalibrate, select, or promote a model.
    The locked test split is used only as a post-certification monitoring
    simulation after Phase 10 and Phase 11/12 were already frozen.
    """

    def __init__(
        self,
        sample_rows: int = 50_000,
    ) -> None:
        if sample_rows < 1:
            raise ValueError(
                "sample_rows must be positive."
            )

        self.sample_rows = sample_rows
        self.model = joblib.load(
            GRAPH_MODEL_PATH
        )

        bundle = joblib.load(
            GRAPH_CALIBRATOR_PATH
        )

        self.calibrator = bundle[
            "calibrator"
        ]
        self.features = list(
            bundle[
                "feature_names"
            ]
        )
        self.categorical = set(
            bundle[
                "categorical_features"
            ]
        )

    def _load_split(
        self,
        split: str,
    ) -> pd.DataFrame:
        frame = (
            pl.scan_parquet(
                GOLD_PATH
            )
            .filter(
                pl.col(
                    "split"
                )
                == split
            )
            .select(
                self.features
            )
            .head(
                self.sample_rows
            )
            .collect()
            .to_pandas()
        )

        if len(frame) == 0:
            raise RuntimeError(
                f"No rows found for split={split}"
            )

        for feature in self.features:
            if feature in self.categorical:
                frame[
                    feature
                ] = (
                    frame[
                        feature
                    ]
                    .astype(str)
                    .astype("category")
                )
            else:
                frame[
                    feature
                ] = pd.to_numeric(
                    frame[
                        feature
                    ],
                    errors="raise",
                )

        return frame

    def _score(
        self,
        frame: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray]:
        raw = np.asarray(
            self.model.predict_proba(
                frame
            )[:, 1],
            dtype=float,
        )

        calibrated = np.asarray(
            self.calibrator.predict_proba(
                raw.reshape(
                    -1,
                    1,
                )
            )[:, 1],
            dtype=float,
        )

        return raw, calibrated

    def run(
        self,
        reference_split: str = "validation",
        monitor_split: str = "test",
    ) -> dict:
        reference = self._load_split(
            reference_split
        )

        monitor = self._load_split(
            monitor_split
        )

        ref_raw, ref_cal = self._score(
            reference
        )

        mon_raw, mon_cal = self._score(
            monitor
        )

        raw_psi = numeric_psi(
            ref_raw,
            mon_raw,
        )

        calibrated_psi = numeric_psi(
            ref_cal,
            mon_cal,
        )

        severities = [
            _severity(
                raw_psi
            ),
            _severity(
                calibrated_psi
            ),
        ]

        overall = (
            "critical"
            if "critical"
            in severities
            else "warning"
            if "warning"
            in severities
            else "stable"
        )

        report = {
            "schema_version":
                "phase13_score_drift_v1",

            "reference_split":
                reference_split,

            "monitor_split":
                monitor_split,

            "reference_rows":
                len(
                    reference
                ),

            "monitor_rows":
                len(
                    monitor
                ),

            "metrics": {
                "graph_score_raw_psi": {
                    "value":
                        raw_psi,
                    "severity":
                        _severity(
                            raw_psi
                        ),
                },

                "graph_score_calibrated_psi": {
                    "value":
                        calibrated_psi,
                    "severity":
                        _severity(
                            calibrated_psi
                        ),
                },
            },

            "overall_severity":
                overall,

            "governance": {
                "automatic_retraining_triggered":
                    False,

                "automatic_recalibration_triggered":
                    False,

                "automatic_model_promotion":
                    False,

                "human_review_required":
                    True,

                "certified_phase10_model":
                    "read_only",

                "test_used_for_model_selection":
                    False,

                "test_used_for_post_lock_monitoring_simulation":
                    True,
            },
        }

        REPORT_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        REPORT_PATH.write_text(
            json.dumps(
                report,
                indent=2,
            ),
            encoding="utf-8",
        )

        return report


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--sample-rows",
        type=int,
        default=50_000,
    )

    args = parser.parse_args()

    report = (
        Phase13ScoreDriftMonitor(
            sample_rows=args.sample_rows
        )
        .run()
    )

    print(
        json.dumps(
            report,
            indent=2,
        )
    )

    print(
        "GRAPHSHIELD_PHASE13_SCORE_DRIFT=PASS"
    )


if __name__ == "__main__":
    main()
