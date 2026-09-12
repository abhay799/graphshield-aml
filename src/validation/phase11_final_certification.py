from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from api.app import app
from explainability.analyst_summary import (
    Phase11AnalystSummaryService,
)
from explainability.explanation_evidence import (
    Phase11ExplanationEvidenceService,
)


PHASE10_CERT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "phase10_certification_v1.json"
)

CONTRACT_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase11"
    / "explanation_contract_v1_report.json"
)

PARITY_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase11"
    / "score_parity_v1_report.json"
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

FINAL_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase11"
    / "phase11_certification_v1.json"
)

REQUIRED_FILES = [
    PROJECT_ROOT
    / "src"
    / "explainability"
    / "explanation_service.py",

    PROJECT_ROOT
    / "src"
    / "explainability"
    / "reason_codes.py",

    PROJECT_ROOT
    / "src"
    / "explainability"
    / "graph_evidence.py",

    PROJECT_ROOT
    / "src"
    / "explainability"
    / "temporal_evidence.py",

    PROJECT_ROOT
    / "src"
    / "explainability"
    / "explanation_bundle.py",

    PROJECT_ROOT
    / "src"
    / "explainability"
    / "case_explanation.py",

    PROJECT_ROOT
    / "src"
    / "explainability"
    / "explanation_evidence.py",

    PROJECT_ROOT
    / "src"
    / "explainability"
    / "analyst_summary.py",

    PROJECT_ROOT
    / "src"
    / "explainability"
    / "persist_explanation.py",

    PROJECT_ROOT
    / "src"
    / "api"
    / "explainability_routes.py",

    PROJECT_ROOT
    / "src"
    / "services"
    / "phase11_case_intelligence.py",
]


def _load_json(
    path: Path,
) -> dict:
    if not path.exists():
        return {}

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower()
            yield from _walk_keys(
                child
            )

    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(
                child
            )


def main() -> None:
    phase10 = _load_json(
        PHASE10_CERT
    )

    contract = _load_json(
        CONTRACT_REPORT
    )

    parity = _load_json(
        PARITY_REPORT
    )

    txid = str(
        pl.read_parquet(
            PREDICTIONS,
            columns=[
                "transaction_id"
            ],
        ).get_column(
            "transaction_id"
        )[0]
    )

    summary = (
        Phase11AnalystSummaryService()
        .build(
            txid,
            top_k=3,
        )
    )

    evidence = (
        Phase11ExplanationEvidenceService()
        .build_documents(
            txid,
            top_k=3,
        )
    )

    keys = set(
        _walk_keys(
            {
                "summary":
                    summary,
                "evidence":
                    evidence,
            }
        )
    )

    openapi_paths = set(
        app.openapi()[
            "paths"
        ].keys()
    )

    required_paths = {
        (
            "/explainability/"
            "transactions/"
            "{transaction_id}"
        ),
        (
            "/explainability/"
            "cases/"
            "{case_id}"
        ),
    }

    required_file_status = {
        str(
            path.relative_to(
                PROJECT_ROOT
            )
        ): path.exists()
        for path in REQUIRED_FILES
    }

    checks = {
        "phase10_certification_pass":
            phase10.get(
                "status"
            ) == "PASS",

        "phase11_contract_pass":
            contract.get(
                "status"
            ) == "PASS",

        "phase11_score_parity_pass":
            parity.get(
                "status"
            ) == "PASS",

        "required_files_present":
            all(
                required_file_status.values()
            ),

        "api_routes_registered":
            required_paths.issubset(
                openapi_paths
            ),

        "explanation_evidence_count":
            len(
                evidence
            ) == 4,

        "ground_truth_not_exposed":
            "is_laundering"
            not in keys,

        "decision_support_only":
            summary[
                "governance"
            ][
                "mode"
            ]
            == "decision_support_only",

        "human_review_required":
            summary[
                "governance"
            ][
                "human_review_required"
            ]
            is True,

        "phase10_artifacts_read_only":
            summary[
                "governance"
            ][
                "certified_phase10_artifacts"
            ]
            == "read_only",

        "autonomous_account_blocking_false":
            summary[
                "governance"
            ][
                "autonomous_account_blocking"
            ]
            is False,

        "autonomous_case_closure_false":
            summary[
                "governance"
            ][
                "autonomous_case_closure"
            ]
            is False,

        "autonomous_regulatory_filing_false":
            summary[
                "governance"
            ][
                "autonomous_regulatory_filing"
            ]
            is False,
    }

    status = (
        "PASS"
        if all(
            checks.values()
        )
        else "FAIL"
    )

    report = {
        "status":
            status,

        "phase":
            11,

        "name":
            "Explainable AML",

        "transaction_id":
            txid,

        "checks":
            checks,

        "required_files":
            required_file_status,

        "registered_explainability_paths":
            sorted(
                path
                for path
                in openapi_paths
                if (
                    "explainability"
                    in path
                )
            ),

        "scientific_boundaries": {
            "tree_shap_scope":
                "frozen_lightgbm_graph_model_only",

            "tgn_explanation":
                "component_score_plus_temporal_context",

            "fusion":
                "frozen_phase10_candidate",

            "test_data_used_for_phase11_tuning":
                False,

            "phase10_models_modified":
                False,
        },

        "governance": {
            "mode":
                "decision_support_only",

            "human_review_required":
                True,

            "autonomous_account_blocking":
                False,

            "autonomous_case_closure":
                False,

            "autonomous_regulatory_filing":
                False,
        },
    }

    FINAL_REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    FINAL_REPORT.write_text(
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
        "GRAPHSHIELD_PHASE11_CERTIFICATION=PASS"
    )


if __name__ == "__main__":
    main()
