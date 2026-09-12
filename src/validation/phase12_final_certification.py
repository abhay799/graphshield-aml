from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from api.app import app
from investigation.phase12_agent import (
    AUDIT_LOG,
    build_plan,
)
from investigation.phase12_audit import (
    verify_hash_chain,
)
from investigation.phase12_grounding import (
    validate_claim_citations,
)
from investigation.phase12_tools import (
    Phase12InvestigationTools,
)


PHASE11_CERT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase11"
    / "phase11_certification_v1.json"
)

FINAL_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase12"
    / "phase12_certification_v1.json"
)

REQUIRED_FILES = [
    PROJECT_ROOT
    / "src"
    / "investigation"
    / "phase12_contracts.py",

    PROJECT_ROOT
    / "src"
    / "investigation"
    / "phase12_tools.py",

    PROJECT_ROOT
    / "src"
    / "investigation"
    / "phase12_contradiction.py",

    PROJECT_ROOT
    / "src"
    / "investigation"
    / "phase12_grounding.py",

    PROJECT_ROOT
    / "src"
    / "investigation"
    / "phase12_audit.py",

    PROJECT_ROOT
    / "src"
    / "investigation"
    / "phase12_agent.py",

    PROJECT_ROOT
    / "src"
    / "api"
    / "phase12_routes.py",
]

PROHIBITED_TOOLS = {
    "block_account",
    "close_account",
    "close_case",
    "file_sar",
    "file_str",
    "submit_regulatory_report",
    "python",
    "shell",
    "powershell",
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def main() -> None:
    phase11 = _load_json(
        PHASE11_CERT
    )

    broad_plan = build_plan(
        case_id="CERTIFICATION_CASE",
        question=(
            "Review transaction history, graph network paths, "
            "risk explanation, FATF policy and regulatory requirements."
        ),
        max_tool_calls=6,
    )

    allowed_tools = {
        item.lower()
        for item in Phase12InvestigationTools.ALLOWED_TOOLS
    }

    grounding_pass = validate_claim_citations(
        (
            "The transaction has prior pair activity "
            "[EVID_ABCDEF1234567890]. "
            "FATF policy context requires human interpretation "
            "[POLICY:fatf_certification_test]. "
            "Human analyst review is required."
        ),
        {
            "EVID_ABCDEF1234567890",
            "POLICY:fatf_certification_test",
        },
    )

    grounding_fail = validate_claim_citations(
        "The transaction definitely proves suspicious conduct.",
        {
            "EVID_ABCDEF1234567890",
        },
    )

    openapi_paths = set(
        app.openapi()[
            "paths"
        ].keys()
    )

    required_paths = {
        "/phase12/tools",
        "/phase12/investigations",
    }

    required_file_status = {
        str(
            path.relative_to(
                PROJECT_ROOT
            )
        ): path.exists()
        for path in REQUIRED_FILES
    }

    audit_status = verify_hash_chain(
        AUDIT_LOG
    )

    checks = {
        "phase11_certification_pass":
            phase11.get(
                "status"
            ) == "PASS",

        "required_files_present":
            all(
                required_file_status.values()
            ),

        "tool_plan_bounded":
            len(
                broad_plan.planned_tools
            )
            <= broad_plan.max_tool_calls
            <= 8,

        "phase11_explanation_tool_present":
            "phase11_explanation"
            in broad_plan.planned_tools,

        "policy_tool_selected":
            "policy_search"
            in broad_plan.planned_tools,

        "graph_tool_selected":
            "path_evidence"
            in broad_plan.planned_tools,

        "history_tool_selected":
            "history_evidence"
            in broad_plan.planned_tools,

        "prohibited_tools_absent":
            PROHIBITED_TOOLS.isdisjoint(
                allowed_tools
            ),

        "strict_grounding_positive_control":
            grounding_pass[
                "passed"
            ]
            is True,

        "strict_grounding_negative_control":
            grounding_fail[
                "passed"
            ]
            is False,

        "api_routes_registered":
            required_paths.issubset(
                openapi_paths
            ),

        "audit_hash_chain_valid":
            audit_status[
                "valid"
            ]
            is True,
    }

    status = (
        "PASS"
        if all(
            checks.values()
        )
        else "FAIL"
    )

    report = {
        "status": status,
        "phase": 12,
        "name": "Agentic Investigation",
        "checks": checks,
        "required_files": required_file_status,
        "allowed_tools": sorted(
            Phase12InvestigationTools.ALLOWED_TOOLS
        ),
        "prohibited_tools": sorted(
            PROHIBITED_TOOLS
        ),
        "certification_plan": broad_plan.model_dump(
            mode="json"
        ),
        "audit_chain": audit_status,
        "registered_phase12_paths": sorted(
            path
            for path in openapi_paths
            if "phase12" in path
        ),
        "governance": {
            "mode":
                "decision_support_only",

            "human_review_required":
                True,

            "read_only_tools_only":
                True,

            "fail_closed_on_grounding_failure":
                True,

            "autonomous_account_blocking":
                False,

            "autonomous_case_closure":
                False,

            "autonomous_regulatory_filing":
                False,
        },
        "scientific_boundaries": {
            "llm_can_call_tools_directly":
                False,

            "planner":
                "deterministic_bounded",

            "claim_level_grounding":
                "strict",

            "phase11_explanations_consumed_as_evidence":
                True,

            "phase10_models_modified":
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
        "GRAPHSHIELD_PHASE12_CERTIFICATION=PASS"
    )


if __name__ == "__main__":
    main()
