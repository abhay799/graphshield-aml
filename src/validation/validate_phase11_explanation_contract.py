from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from explainability.explanation_bundle import (
    Phase11ExplanationBundleService,
)


PREDICTIONS = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
    / "v2"
    / "phase10"
    / "locked_test_predictions_v1.parquet"
)

REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase11"
    / "explanation_contract_v1_report.json"
)


FORBIDDEN_KEYS = {
    "is_laundering",
    "target",
    "label",
    "ground_truth",
}


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def main() -> None:
    if not PREDICTIONS.exists():
        raise FileNotFoundError(PREDICTIONS)

    txid = str(
        pl.read_parquet(
            PREDICTIONS,
            columns=["transaction_id"],
        ).get_column("transaction_id")[0]
    )

    service = Phase11ExplanationBundleService()

    result = service.build(
        transaction_id=txid,
        top_k=8,
    )

    keys = {
        key.lower()
        for key in walk_keys(result)
    }

    forbidden_found = sorted(
        key
        for key in FORBIDDEN_KEYS
        if key in keys
    )

    checks = {
        "schema_version_present":
            result.get("schema_version")
            == "phase11_explanation_bundle_v1",

        "phase10_candidate_present":
            bool(
                result.get(
                    "phase10_final_candidate"
                )
            ),

        "tree_shap_graph_only":
            result[
                "explanation_boundaries"
            ][
                "tree_shap_applies_to_graph_lightgbm_only"
            ]
            is True,

        "tgn_not_shap":
            result[
                "explanation_boundaries"
            ][
                "tgn_explained_with_temporal_context_not_shap"
            ]
            is True,

        "ground_truth_not_exposed":
            not forbidden_found,

        "decision_support_only":
            result[
                "governance"
            ][
                "mode"
            ]
            == "decision_support_only",

        "human_review_required":
            result[
                "governance"
            ][
                "human_review_required"
            ]
            is True,

        "phase10_read_only":
            result[
                "governance"
            ][
                "certified_phase10_artifacts"
            ]
            == "read_only",

        "autonomous_account_blocking_false":
            result[
                "governance"
            ][
                "autonomous_account_blocking"
            ]
            is False,

        "autonomous_case_closure_false":
            result[
                "governance"
            ][
                "autonomous_case_closure"
            ]
            is False,

        "autonomous_regulatory_filing_false":
            result[
                "governance"
            ][
                "autonomous_regulatory_filing"
            ]
            is False,
    }

    status = (
        "PASS"
        if all(checks.values())
        else "FAIL"
    )

    report = {
        "status": status,
        "phase": 11,
        "block": "explanation-contract",
        "transaction_id": txid,
        "checks": checks,
        "forbidden_keys_found": forbidden_found,
    }

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            report,
            indent=2,
        )
    )

    if status != "PASS":
        raise SystemExit(2)

    print(
        "GRAPHSHIELD_PHASE11_EXPLANATION_CONTRACT=PASS"
    )


if __name__ == "__main__":
    main()
