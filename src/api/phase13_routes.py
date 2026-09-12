from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHASE13_DIR = PROJECT_ROOT / "reports" / "v2" / "phase13"

router = APIRouter(prefix="/phase13", tags=["phase13-governance"])


def _read_report(name: str) -> dict[str, Any]:
    path = PHASE13_DIR / name
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Phase 13 report unavailable: {name}",
        )
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/status")
def phase13_status() -> dict[str, Any]:
    return _read_report("governance_status_v1_report.json")


@router.get("/drift")
def phase13_drift() -> dict[str, Any]:
    return _read_report("drift_investigation_v1_report.json")


@router.get("/performance")
def phase13_performance() -> dict[str, Any]:
    return _read_report("performance_monitor_v1_report.json")


@router.get("/retraining-proposal")
def phase13_retraining_proposal() -> dict[str, Any]:
    return _read_report("retraining_review_proposal_v1_report.json")


@router.get("/governance-gate")
def phase13_governance_gate() -> dict[str, Any]:
    return _read_report("governance_gate_v1_report.json")
