from __future__ import annotations

import json
from pathlib import Path

import joblib
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "lightgbm_graph_v1.joblib"
)

FEATURE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "live_feature_contract_v1.json"
)


DIRECT_EVENT_FIELDS = {
    "amount_paid",
    "amount_received",
    "payment_format",
    "payment_currency",
    "receiving_currency",
}


def main():

    print("=" * 88)
    print(
        "GraphShield AML - Phase 10 "
        "- Live Feature Contract Audit"
    )
    print("=" * 88)

    model = joblib.load(
        MODEL_PATH
    )

    model_features = list(
        model.feature_name_
    )

    schema = (
        pl.scan_parquet(
            FEATURE_PATH
        )
        .collect_schema()
    )

    schema_names = set(
        schema.names()
    )

    missing_from_store = [
        feature
        for feature in model_features
        if feature not in schema_names
    ]

    direct = [
        feature
        for feature in model_features
        if feature in DIRECT_EVENT_FIELDS
    ]

    stateful = [
        feature
        for feature in model_features
        if feature not in DIRECT_EVENT_FIELDS
    ]

    label_like = [
        feature
        for feature in model_features
        if (
            "launder" in feature.lower()
            or "label" in feature.lower()
            or "target" in feature.lower()
        )
    ]

    if missing_from_store:
        raise RuntimeError(
            "Frozen model feature(s) missing from "
            f"certified store: {missing_from_store}"
        )

    if label_like:
        raise RuntimeError(
            "Potential label leakage in model contract: "
            f"{label_like}"
        )

    report = {
        "status": "PASS",
        "phase": 10,
        "block": "B1",
        "model": "lightgbm_graph_v1",
        "feature_store":
            str(
                FEATURE_PATH.relative_to(
                    PROJECT_ROOT
                )
            ),
        "total_model_features":
            len(model_features),
        "direct_event_features":
            direct,
        "stateful_features":
            stateful,
        "missing_from_certified_store":
            missing_from_store,
        "label_like_features":
            label_like,
        "model_features":
            model_features,
        "require_exact_online_parity":
            True,
        "zero_fill_missing_features":
            False,
        "label_leakage_allowed":
            False,
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

    print(
        f"TOTAL_MODEL_FEATURES="
        f"{len(model_features)}"
    )

    print(
        f"DIRECT_EVENT_FEATURES="
        f"{len(direct)}"
    )

    print(
        f"STATEFUL_FEATURES="
        f"{len(stateful)}"
    )

    print("\n=== DIRECT ===")

    for name in direct:
        print(name)

    print("\n=== STATEFUL ===")

    for name in stateful:
        print(name)

    print(
        "\nMISSING_FROM_CERTIFIED_STORE=0"
    )

    print(
        "LABEL_LEAKAGE=NONE"
    )

    print(
        "ZERO_FILL_MISSING_FEATURES=FALSE"
    )

    print(
        f"REPORT={REPORT_PATH}"
    )

    print(
        "GRAPHSHIELD_PHASE10_BLOCK_B1=PASS"
    )


if __name__ == "__main__":
    main()