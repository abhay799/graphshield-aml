from __future__ import annotations

from functools import lru_cache

from fastapi import (
    APIRouter,
    HTTPException,
)

from pydantic import (
    BaseModel,
    Field,
)

from services.case_intelligence import (
    CaseIntelligenceService,
)


router = APIRouter(
    tags=[
        "case-intelligence"
    ]
)


@lru_cache(maxsize=1)
def get_case_intelligence_service():

    return CaseIntelligenceService(
        enable_policy_reranker=False
    )


class CaseIntelligenceRequest(
    BaseModel
):

    question: str | None = Field(
        default=None,
        max_length=4000,
    )

    evidence_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    include_policy: bool = True

    policy_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    jurisdiction: str | None = None


@router.post(
    "/cases/{case_id}/intelligence"
)
def case_intelligence(
    case_id: str,
    request: CaseIntelligenceRequest,
):

    try:

        return (
            get_case_intelligence_service()
            .build(
                case_id=
                    case_id,

                question=
                    request.question,

                evidence_top_k=
                    request.evidence_top_k,

                include_policy=
                    request.include_policy,

                policy_top_k=
                    request.policy_top_k,

                jurisdiction=
                    request.jurisdiction,
            )
        )

    except KeyError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error).strip("'"),
        ) from error

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
