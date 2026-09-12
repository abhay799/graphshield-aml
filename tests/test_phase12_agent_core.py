from __future__ import annotations

from pathlib import Path

import polars as pl

from investigation.phase12_agent import (
    build_plan,
)
from investigation.phase12_contracts import (
    ToolCallRequest,
)
from investigation.phase12_tools import (
    Phase12InvestigationTools,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CASE_QUEUE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)


def _case_id() -> str:
    schema = pl.read_parquet_schema(
        CASE_QUEUE
    )
    names = set(
        schema.names()
    )

    case_column = next(
        name
        for name in (
            "case_id",
            "investigation_id",
            "alert_id",
        )
        if name in names
    )

    return str(
        pl.read_parquet(
            CASE_QUEUE,
            columns=[case_column],
        ).get_column(
            case_column
        )[0]
    )


def test_phase12_plan_is_bounded_and_policy_aware():
    plan = build_plan(
        case_id=_case_id(),
        question=(
            "Review transaction history, graph paths, "
            "and relevant FATF policy."
        ),
        max_tool_calls=6,
    )

    assert len(
        plan.planned_tools
    ) <= 6

    assert (
        "phase11_explanation"
        in plan.planned_tools
    )

    assert (
        "policy_search"
        in plan.planned_tools
    )

    assert (
        "path_evidence"
        in plan.planned_tools
    )

    assert (
        "history_evidence"
        in plan.planned_tools
    )


def test_phase12_tool_allowlist_has_no_action_tools():
    tools = Phase12InvestigationTools()

    prohibited = {
        "block_account",
        "close_account",
        "close_case",
        "file_sar",
        "file_str",
        "submit_regulatory_report",
        "python",
        "shell",
    }

    assert prohibited.isdisjoint(
        {
            item.lower()
            for item in tools.ALLOWED_TOOLS
        }
    )


def test_phase12_case_overview_tool_is_read_only():
    case_id = _case_id()

    result = (
        Phase12InvestigationTools()
        .execute(
            ToolCallRequest(
                tool_name="case_overview",
                case_id=case_id,
                top_k=5,
            )
        )
    )

    assert result.tool_name == (
        "case_overview"
    )

    assert result.success is True
    assert result.error is None
    assert isinstance(
        result.payload,
        list,
    )
