from __future__ import annotations

from typing import Any

from investigation.phase12_contracts import (
    ContradictionFinding,
    ToolCallResult,
)


def _collect_phase11_drivers(
    tool_results: list[ToolCallResult],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    risk: list[dict[str, Any]] = []
    protective: list[dict[str, Any]] = []

    for result in tool_results:
        if (
            result.tool_name
            != "phase11_explanation"
            or not result.success
            or not isinstance(
                result.payload,
                dict,
            )
        ):
            continue

        explanation = result.payload.get(
            "explanation",
            {},
        )

        reason_codes = explanation.get(
            "reason_codes",
            {},
        )

        risk.extend(
            reason_codes.get(
                "risk_drivers",
                [],
            )
        )

        protective.extend(
            reason_codes.get(
                "protective_drivers",
                [],
            )
        )

    return risk, protective


def build_contradiction_findings(
    tool_results: list[ToolCallResult],
) -> list[ContradictionFinding]:
    """
    Deterministic contradiction/counter-evidence layer.

    We do not manufacture a binary "contradiction". Instead we surface
    both risk-raising and risk-lowering certified model evidence and
    explicitly mark insufficient evidence when retrieval is empty.
    """

    findings: list[
        ContradictionFinding
    ] = []

    risk, protective = (
        _collect_phase11_drivers(
            tool_results
        )
    )

    if risk:
        findings.append(
            ContradictionFinding(
                finding_type="supporting",
                title=(
                    "Risk-raising model evidence "
                    "is present."
                ),
                evidence_refs=[
                    item.get(
                        "reason_code",
                        "",
                    )
                    for item in risk[:5]
                    if item.get(
                        "reason_code"
                    )
                ],
                detail=(
                    "The frozen LightGBM graph model "
                    "contains positive TreeSHAP drivers. "
                    "These are model attributions, not "
                    "proof of wrongdoing."
                ),
            )
        )

    if protective:
        findings.append(
            ContradictionFinding(
                finding_type="countervailing",
                title=(
                    "Risk-lowering model evidence "
                    "is also present."
                ),
                evidence_refs=[
                    item.get(
                        "reason_code",
                        "",
                    )
                    for item in protective[:5]
                    if item.get(
                        "reason_code"
                    )
                ],
                detail=(
                    "The frozen LightGBM graph model "
                    "also contains negative TreeSHAP "
                    "drivers that lower modeled risk."
                ),
            )
        )

    retrieved = sum(
        len(result.evidence_ids)
        for result in tool_results
        if result.success
    )

    successful_tools = sum(
        1
        for result in tool_results
        if result.success
    )

    if (
        retrieved == 0
        and successful_tools == 0
    ):
        findings.append(
            ContradictionFinding(
                finding_type="insufficient",
                title="Insufficient investigation evidence.",
                evidence_refs=[],
                detail=(
                    "No Phase 12 investigation tool "
                    "returned usable evidence."
                ),
            )
        )

    return findings
