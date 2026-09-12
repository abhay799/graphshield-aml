from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from investigation.phase12_agent import (
    Phase12InvestigationAgent,
)
from investigation.phase12_tools import (
    Phase12InvestigationTools,
)


router = APIRouter(
    prefix="/phase12",
    tags=["phase12-investigation"],
)


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    question: str = Field(
        min_length=1,
        max_length=4000,
    )


@lru_cache(maxsize=1)
def get_agent() -> Phase12InvestigationAgent:
    return Phase12InvestigationAgent()


@router.get("/tools")
def list_tools():
    return {
        "mode": "read_only",
        "tools": sorted(
            Phase12InvestigationTools.ALLOWED_TOOLS
        ),
        "human_review_required": True,
        "autonomous_account_blocking": False,
        "autonomous_case_closure": False,
        "autonomous_regulatory_filing": False,
    }


@router.post("/investigations")
def run_investigation(
    request: InvestigationRequest,
):
    try:
        result = get_agent().run(
            case_id=request.case_id,
            question=request.question,
        )

        return result.model_dump(
            mode="json"
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Phase 12 investigation failed: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc
