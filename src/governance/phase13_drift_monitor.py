from __future__ import annotations

import argparse
import json
import math
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

from governance.phase13_contracts import (
    DriftReport,
    FeatureDriftMetric,
)


GOLD_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
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
    / "feature_drift_v1_report.json"
)

EPSILON = 1e-6


def _severity(
    value: float,
) -> str:
    # Monitoring heuristic, not an automatic retraining rule.
    if value < 0.10:
        return "stable"

    if value < 0.25:
        return "warning"

    return "critical"


def _overall(
    severities: list[str],
) -> str:
    if "critical" in severities:
        return "critical"

    if "warning" in severities:
        return "warning"

    return "stable"


def numeric_psi(
    reference: pd.Series,
    monitor: pd.Series,
    bins: int = 10,
) -> float:
    ref = pd.to_numeric(
        reference,
        errors="coerce",
    ).dropna()

    mon = pd.to_numeric(
        monitor,
        errors="coerce",
    ).dropna()

    if len(ref) == 0 or len(mon) == 0:
        return 0.0

    quantiles = np.linspace(
        0.0,
        1.0,
        bins + 1,
    )

    edges = np.unique(
        np.quantile(
            ref.to_numpy(),
            quantiles,
        )
    )

    if len(edges) < 3:
        return 0.0

    edges = edges.astype(
        float
    )

    edges[0] = -np.inf
    edges[-1] = np.inf

    ref_counts, _ = np.histogram(
        ref.to_numpy(),
        bins=edges,
    )

    mon_counts, _ = np.histogram(
        mon.to_numpy(),
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


def categorical_tvd(
    reference: pd.Series,
    monitor: pd.Series,
) -> tuple[float, float]:
    ref = reference.fillna(
        "__MISSING__"
    ).astype(str)

    mon = monitor.fillna(
        "__MISSING__"
    ).astype(str)

    ref_freq = ref.value_counts(
        normalize=True
    )

    mon_freq = mon.value_counts(
        normalize=True
    )

    categories = sorted(
        set(
            ref_freq.index
        )
        | set(
            mon_freq.index
        )
    )

    distance = 0.5 * sum(
        abs(
            float(
                ref_freq.get(
                    category,
                    0.0,
                )
            )
            - float(
                mon_freq.get(
                    category,
                    0.0,
                )
            )
        )
        for category in categories
    )

    unseen = set(
        mon.unique()
    ) - set(
        ref.unique()
    )

    unseen_rate = float(
        mon.isin(
            unseen
        ).mean()
    ) if unseen else 0.0

    return float(
        distance
    ), unseen_rate


class Phase13DriftMonitor:
    """
    Frozen-model feature drift monitor.

    Reference: validation split.
    Monitor: test split as a post-lock simulation window.

    Test is NOT used for tuning, threshold optimization, model selection,
    retraining, or calibration. This script only measures post-lock drift.
    """

    def __init__(
        self,
        sample_rows: int = 100_000,
    ) -> None:
        if sample_rows < 1:
            raise ValueError(
                "sample_rows must be positive."
            )

        self.sample_rows = sample_rows

        bundle = joblib.load(
            GRAPH_CALIBRATOR_PATH
        )

        self.features = list(
            bundle["feature_names"]
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

        return frame

    def run(
        self,
        reference_split: str = "validation",
        monitor_split: str = "test",
    ) -> DriftReport:
        reference = self._load_split(
            reference_split
        )

        monitor = self._load_split(
            monitor_split
        )

        metrics = []

        for feature in self.features:
            ref = reference[
                feature
            ]

            mon = monitor[
                feature
            ]

            missing_ref = float(
                ref.isna().mean()
            )

            missing_mon = float(
                mon.isna().mean()
            )

            if feature in self.categorical:
                metric_value, unseen_rate = (
                    categorical_tvd(
                        ref,
                        mon,
                    )
                )

                metric_name = (
                    "total_variation_distance"
                )

                feature_type = (
                    "categorical"
                )
            else:
                metric_value = (
                    numeric_psi(
                        ref,
                        mon,
                    )
                )

                unseen_rate = None
                metric_name = "psi"
                feature_type = "numeric"

            metrics.append(
                FeatureDriftMetric(
                    feature=feature,
                    feature_type=feature_type,
                    metric_name=metric_name,
                    metric_value=metric_value,
                    missing_rate_reference=
                        missing_ref,
                    missing_rate_monitor=
                        missing_mon,
                    missing_rate_delta=(
                        missing_mon
                        - missing_ref
                    ),
                    unseen_category_rate=
                        unseen_rate,
                    severity=_severity(
                        metric_value
                    ),
                )
            )

        report = DriftReport(
            reference_split=
                reference_split,
            monitor_split=
                monitor_split,
            reference_rows=len(
                reference
            ),
            monitor_rows=len(
                monitor
            ),
            feature_metrics=
                metrics,
            overall_severity=
                _overall(
                    [
                        item.severity
                        for item
                        in metrics
                    ]
                ),
        )

        REPORT_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        REPORT_PATH.write_text(
            json.dumps(
                report.model_dump(
                    mode="json"
                ),
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
        default=100000,
    )

    args = parser.parse_args()

    report = (
        Phase13DriftMonitor(
            sample_rows=args.sample_rows
        )
        .run()
    )

    print(
        json.dumps(
            report.model_dump(
                mode="json"
            ),
            indent=2,
        )
    )

    print(
        "GRAPHSHIELD_PHASE13_DRIFT_MONITOR=PASS"
    )


if __name__ == "__main__":
    main()
